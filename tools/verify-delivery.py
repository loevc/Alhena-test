"""Audit the current Windows deliverable against build, GUI and measurement evidence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
checks = []


def require(condition, message):
    if not condition:
        raise RuntimeError(message)
    checks.append(message)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def git(directory, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={directory.as_posix()}", "-C", str(directory), *args], text=True, encoding="utf-8").strip()


parser = argparse.ArgumentParser()
parser.add_argument("--archive", required=True, type=Path)
parser.add_argument("--gui", required=True, type=Path)
parser.add_argument("--workflow", required=True, type=Path)
parser.add_argument("--product", required=True, type=Path)
parser.add_argument("--baseline-measurement", required=True, type=Path)
parser.add_argument("--measurement", required=True, type=Path)
parser.add_argument("--output", default=Path("out/reports/delivery.json"), type=Path)
args = parser.parse_args()
lock = read(ROOT / "upstream.lock.json")
source_root = ROOT / lock["checkout"]
archive_hash = digest(args.archive)
require(git(source_root, "rev-parse", "HEAD") == lock["commit"], "Official upstream HEAD matches the pinned commit")
managed = read(source_root / ".alhena-overlay.json")
require(all(digest(source_root / name) == value for name, value in managed.items()), "Prepared overlays and pinned compatibility patches have no local drift")
product_hashes = {}
for path in (ROOT / "product").rglob("*"):
    if not path.is_file():
        continue
    relative = path.relative_to(ROOT / "product")
    if relative.parts[0] in ("build", "platform-build"):
        base = "build/src/alhena" if relative.parts[0] == "build" else "platform/build-scripts/src/alhena"
        target = source_root / base / Path(*relative.parts[1:])
    else:
        target = source_root / "alhena" / relative
    require(path.read_bytes() == target.read_bytes(), f"Current product source prepared: {relative.as_posix()}")
    product_hashes[relative.as_posix()] = digest(path)
ignored = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), "check-ignore", "product/build/AlhenaProperties.kt", "product/build/AlhenaBuildTarget.kt"], capture_output=True)
require(ignored.returncode == 1, "Essential product build sources are not ignored by Git")
with zipfile.ZipFile(args.archive) as package:
    names = set(package.namelist())
    require({"bin/alhena64.exe", "jbr/bin/java.exe", "LICENSE.txt", "NOTICE.txt", "product-info.json"} <= names, "Native launcher, runtime, product metadata and notices are present")
    info = json.loads(package.read("product-info.json"))
    require(info["name"] == "Alhena" and info["productCode"] == "AL", "Archive declares the independent Alhena product")
    require("21.0.9" in package.read("jbr/release").decode() and "jdk.jcef" not in package.read("jbr/release").decode(), "Bundled runtime is the pinned lightweight JBR 21.0.9")
    plugins = {name.split("/")[1] for name in names if name.startswith("plugins/") and len(name.split("/")) > 2}
    require(plugins == {"vcs-git"}, "Only the original Git plugin is bundled")
    excluded = {line.strip() for line in (ROOT / "product/resources/alhena-excluded-modules.txt").read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
    require(all(f"lib/modules/{name}.jar" not in names for name in excluded), "All six excluded runtime module JARs are absent")
    for name in ("LICENSE.txt", "NOTICE.txt"):
        require(package.read(name) == (source_root / name).read_bytes(), f"Upstream {name} is preserved byte-for-byte")
    compiled = source_root / "out/alhena/classes/production/alhena.product"
    classes = list((compiled / "alhena").rglob("*.class"))
    with zipfile.ZipFile(io.BytesIO(package.read("lib/app.jar"))) as app:
        require(len(classes) >= 6 and all(app.read(path.relative_to(compiled).as_posix()) == path.read_bytes() for path in classes), "Packaged Alhena classes match the current JPS compiler output")
metadata = read(source_root / "out/alhena/artifacts/AL-builtinModules.json")
require(metadata["plugins"] == ["Git4Idea", "com.intellij"], "Upstream bundled-plugin self-check enables Git4Idea and platform core")
dependency_report = read(ROOT / "out/reports/dependencies.json")
require(not dependency_report["unresolvedDependencies"] and not dependency_report["descriptorInventory"]["parseErrors"], "Production dependency audit has no missing dependencies or malformed descriptors")
results = {}
for kind in ("gui", "workflow", "product"):
    result = read(getattr(args, kind))
    require(result["status"] == "passed" and result["archiveSha256"] == archive_hash, f"{kind} acceptance passed on this exact archive")
    results[kind] = result
gui_text = (Path(results["gui"]["evidence"]) / "inspect.txt").read_text(encoding="utf-8")
require("VcsLogMainGraphTable showing=true rows=5" in gui_text and "BRANCH:feature/history" in gui_text and "Twoside" in gui_text, "Actual GUI snapshot contains commit graph, branch tree and two-sided Diff")
workflow = results["workflow"]
repository = Path(workflow["fixture"]["repository"])
require(repository.resolve().is_relative_to((ROOT / "out/fixtures").resolve()), "Mutating workflow acceptance uses a dedicated fixture repository")
require(git(repository, "rev-parse", "HEAD") == workflow["head"] and git(repository, "log", "-1", "--format=%P").split() == workflow["parents"] and len(workflow["parents"]) == 2, "Actual fixture HEAD is the accepted two-parent merge commit")
require(not git(repository, "status", "--porcelain") and not git(repository, "ls-files", "-u") and not (repository / ".git/MERGE_HEAD").exists(), "Actual fixture index and working tree are clean, with no unfinished merge")
require(git(Path(workflow["fixture"]["remote"]), "rev-parse", "main") in workflow["parents"], "Local test remote update is represented in the final merge parents")
product_text = (Path(results["product"]["evidence"]) / "project/ui-inspect.txt").read_text(encoding="utf-8")
require("toolWindow=Version Control visible=true" in product_text and "commitMode=GitStagingAreaCommitMode" in product_text and "updates.platform=false plugins=false" in product_text and "provider=alhena.AlhenaConsent" in product_text, "Native first-launch snapshot proves the Git layout and independent settings")
datasets = [read(args.baseline_measurement), read(args.measurement)]
for dataset in datasets:
    require(all(sample.get("shutdownClean") is True and sample["runningProgressIndicators"] == 0 and sample["heapUsedBytes"] > 0 for sample in dataset["samples"]), f"{dataset['label']} samples have measured heap, quiet progress and clean shutdown")
    for scenario in ("empty-fresh", "repository-fresh", "repository-cached"):
        require(len([sample for sample in dataset["samples"] if sample["scenario"] == scenario and not sample["warmup"]]) >= 3, f"{dataset['label']}: at least three {scenario} samples")
    for sample in dataset["samples"]:
        launch = read(Path(sample["evidence"]) / "launch.json")
        log = (Path(launch["sandbox"]) / "log/idea.log").read_text(encoding="utf-8")
        require(not re.search(r"\] (?:SEVERE|\s*ERROR) - ", log) and "NOT_CLOSED_PROPERLY" not in log, f"Measurement log is clean: {dataset['label']}/{sample['scenario']}/{sample['iteration']}")
require(all(sample["archiveSha256"] == archive_hash for sample in datasets[1]["samples"]), "All final measurements use this exact archive")
require(all(datasets[0]["machine"][key] == datasets[1]["machine"][key] for key in ("cpu", "osVersion", "physicalMemoryBytes", "upstream")), "Before/after measurements use the same machine and upstream baseline")
report = {"status": "passed", "scope": "Current Windows platform-product plan A-E", "archive": str(args.archive.resolve()), "archiveSha256": archive_hash, "archiveBytes": args.archive.stat().st_size, "upstream": lock["commit"], "productSources": product_hashes, "evidence": {kind: str(getattr(args, kind).resolve()) for kind in ("gui", "workflow", "product")}, "measurements": [str(args.baseline_measurement.resolve()), str(args.measurement.resolve())], "checks": checks}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": "passed", "checks": len(checks), "archiveSha256": archive_hash, "report": str(args.output.resolve())}, indent=2))
