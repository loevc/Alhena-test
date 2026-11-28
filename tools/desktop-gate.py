"""Run isolated Windows desktop suites serially against one immutable ZIP.

Requires an interactive desktop and the build bootstrap JDK. This is a local
acceptance gate, not a declaration that a package is ready for release.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "native-switch": ("welcome-smoke", "powershell", ["-NativeSelection", "-ExistingProject", "-SwitchRepositories", "-FixtureSuffix", " desktop 中文 repo"]),
    "cli-ps51": ("welcome-smoke", "powershell", ["-CommandLine", "-ExistingProject", "-FixtureSuffix", " desktop 中文 repo"]),
    "cli-ps7": ("welcome-smoke", "pwsh", ["-CommandLine", "-ExistingProject", "-FixtureSuffix", " desktop 中文 repo"]),
    "product": ("product-smoke", "pwsh", []),
    "graph-diff": ("smoke", "pwsh", []),
    "workflow": ("workflow-smoke", "pwsh", []),
    "workspace": ("workspace-git-smoke", "pwsh", []),
    "advanced": ("advanced-git-smoke", "pwsh", []),
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(report, folder):
    """Check required coverage, copied evidence integrity, ZIP and source identity."""
    if report.get("status") != "passed" or set(report.get("cases", {})) != set(CASES):
        raise ValueError("Incomplete desktop gate")
    archive_hash = report["archiveSha256"]
    if digest(report["archive"]) != archive_hash:
        raise ValueError("Archive changed")
    for name, item in report["cases"].items():
        path = Path(folder) / (name + ".json")
        if digest(path) != item["resultSha256"]:
            raise ValueError("Evidence changed: " + name)
        result = read(path)
        if result.get("status") != "passed" or result.get("archiveSha256") != archive_hash:
            raise ValueError("Failed case or mixed archives: " + name)
        if not result.get("checks"):
            raise ValueError("Missing checks: " + name)
        if result.get("evidence") != item["originalEvidence"]:
            raise ValueError("Evidence identity mismatch: " + name)
        if name == "native-switch" and not all(result.get(key) for key in ("repositorySwitching", "nativeSelection", "existingProject")):
            raise ValueError("Missing native switching coverage")
        if name.startswith("cli-"):
            version = "5.1." if name == "cli-ps51" else "7."
            if not result.get("commandLineMode") or not result.get("existingProject") or not result.get("powerShellVersion", "").startswith(version):
                raise ValueError("Wrong command-line coverage: " + name)
    for relative, expected in report["sourceSha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Source changed: " + relative)


def source_hashes():
    paths = [ROOT / "upstream.lock.json", ROOT / "run.ps1", ROOT / "build.ps1"]
    for directory in ("product", "tools", "tests", "patches", "build-support", ".github"):
        paths.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                     and p != ROOT / "build-support/iteration-plan.json")
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


def run(archive):
    if os.name != "nt":
        raise RuntimeError("An interactive Windows desktop is required")
    archive = archive.resolve(strict=True)
    shells = {name: shutil.which(name + ".exe") for name in ("powershell", "pwsh")}
    if not all(shells.values()):
        raise RuntimeError("Windows PowerShell 5.1 and PowerShell 7 are both required")
    folder = ROOT / "out/desktop-gate" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    report = {"status": "running", "startedAtUtc": datetime.now(timezone.utc).isoformat(),
              "archive": str(archive), "archiveSha256": digest(archive), "archiveBytes": archive.stat().st_size,
              "sourceSha256": source_hashes(), "cases": {}, "realRemoteCoverage": "not_run",
              "releaseReady": False, "limits": ["Real remote matrix is separate", "Commit/tag/Release association and P2 remain"]}
    save(folder / "result.json", report)
    environment = os.environ.copy()
    # A PowerShell 7 parent can put incompatible modules ahead of the 5.1
    # modules. Let each child shell initialize its own standard module path.
    environment = {key: value for key, value in environment.items() if key.upper() != "PSMODULEPATH"}
    try:
        for name, (suite, shell, arguments) in CASES.items():
            print("Running " + name, flush=True)
            output_root = ROOT / "out" / ("gui-smoke" if suite == "smoke" else suite)
            before = set(output_root.glob("*/result.json"))
            command = [shells[shell], "-NoProfile", "-File", str(ROOT / "tools" / (suite + ".ps1")), "-Archive", str(archive), *arguments]
            with (folder / (name + ".log")).open("wb") as log:
                subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            fresh = set(output_root.glob("*/result.json")) - before
            if len(fresh) != 1:
                raise RuntimeError("Expected exactly one fresh result: " + name)
            original = fresh.pop()
            result = read(original)
            if result.get("status") != "passed" or result.get("archiveSha256") != report["archiveSha256"]:
                raise RuntimeError("Failed case or mixed archives: " + name)
            copied = folder / (name + ".json")
            shutil.copyfile(original, copied)
            report["cases"][name] = {"resultSha256": digest(copied), "originalEvidence": result["evidence"]}
            save(folder / "result.json", report)
        report["status"] = "passed"
        validate(report, folder)
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
        save(folder / "result.json", report)
        print(str(folder / "result.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--archive", type=Path)
    group.add_argument("--verify", type=Path, help="Verify a completed gate against current source and ZIP")
    args = parser.parse_args()
    if args.verify:
        validate(read(args.verify), args.verify.parent)
        print("Desktop evidence verified; release readiness is tracked separately.")
    else:
        run(args.archive)
