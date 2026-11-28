"""Run the explicitly authorized Alhena-test remote matrix and revoke its test key."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys

from importlib.util import module_from_spec, spec_from_file_location

spec = spec_from_file_location("desktop_gate", Path(__file__).with_name("desktop-gate.py"))
gate = module_from_spec(spec)
spec.loader.exec_module(gate)
ROOT = gate.ROOT


def run(context, archive):
    context = context.resolve(strict=True)
    if not context.is_relative_to(ROOT / ".cache/remote-test"):
        raise ValueError("Context outside remote test cache")
    fixture = gate.read(context)
    if fixture.get("repository") != "loevc/Alhena-test" or fixture.get("status") != "ready":
        raise ValueError("Inactive or unauthorized fixture")
    archive = archive.resolve(strict=True)
    shell = shutil.which("pwsh.exe")
    if not shell:
        raise RuntimeError("PowerShell 7 is required")
    folder = ROOT / "out/remote-matrix" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    report = {"status": "running", "startedAtUtc": datetime.now(timezone.utc).isoformat(),
              "archive": str(archive), "archiveSha256": gate.digest(archive),
              "sourceSha256": gate.source_hashes(),
              "repository": fixture["repository"], "cases": {}, "temporaryKeyRevoked": False,
              "releaseReady": False,
              "limits": ["Network failure uses an unreachable per-process proxy; physical disconnect/reconnect is not covered"]}

    def case(name, suite, arguments):
        print("Running " + name, flush=True)
        output = ROOT / "out" / ("welcome-smoke" if suite == "welcome-smoke" else "remote-sync")
        before = set(output.glob("*/result.json"))
        command = [shell, "-NoProfile", "-File", str(ROOT / "tools" / (suite + ".ps1")), "-Archive", str(archive), *arguments]
        with (folder / (name + ".log")).open("wb") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900, check=True)
        fresh = set(output.glob("*/result.json")) - before
        if len(fresh) != 1:
            raise RuntimeError("Expected one fresh result: " + name)
        original = fresh.pop()
        result = gate.read(original)
        if result.get("status") != "passed" or result.get("archiveSha256") != report["archiveSha256"]:
            raise RuntimeError("Failed case or mixed ZIP: " + name)
        copied = folder / (name + ".json")
        shutil.copyfile(original, copied)
        report["cases"][name] = {"resultSha256": gate.digest(copied), "originalEvidence": result["evidence"]}
        gate.save(folder / "result.json", report)
        return str(original)

    gate.save(folder / "result.json", report)
    try:
        clones = {}
        for transport in ("https", "ssh"):
            clones[transport] = case(transport + "-clone", "welcome-smoke", ["-RemoteContext", str(context), "-Transport", transport])
            case(transport + "-sync", "remote-sync-smoke", ["-Context", str(context), "-CloneResult", clones[transport]])
        case("https-auth-cancel", "remote-sync-smoke", ["-Context", str(context), "-CloneResult", clones["https"], "-CancelAuthentication"])
        case("ssh-auth-rejected", "welcome-smoke", ["-RemoteContext", str(context), "-Transport", "ssh", "-RejectedAuthentication"])
        case("network-failure", "welcome-smoke", ["-RemoteContext", str(context), "-Transport", "https", "-UnavailableNetwork"])
        if gate.digest(archive) != report["archiveSha256"]:
            raise RuntimeError("Archive changed during remote matrix")
        if gate.source_hashes() != report["sourceSha256"]:
            raise RuntimeError("Source changed during remote matrix")
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            with (folder / "cleanup.log").open("wb") as log:
                subprocess.run([sys.executable, str(ROOT / "tools/remote-fixture.py"), "cleanup", "--context", str(context)],
                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True)
            cleaned = gate.read(context)
            report["temporaryKeyRevoked"] = cleaned.get("status") == "cleaned" and cleaned.get("deployKeyId") is None and not Path(cleaned["privateKeyPath"]).exists()
            if not report["temporaryKeyRevoked"]:
                raise RuntimeError("Temporary key cleanup not confirmed")
        except BaseException:
            report.update(status="failed", cleanupError="Temporary key revocation needs attention; see cleanup.log")
            raise
        finally:
            report["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
            gate.save(folder / "result.json", report)
            print(str(folder / "result.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    run(args.context, args.archive)
