"""Compare ZIP contents and content modules listed by upstream's plugin lister."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def inventory(archive, metadata):
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        runtime = package.read("jbr/release").decode("utf-8")
        result = {
            "archive": str(archive.resolve()),
            "sha256": digest.hexdigest(),
            "archiveBytes": archive.stat().st_size,
            "uncompressedBytes": sum(item.file_size for item in package.infolist()),
            "entries": len(names),
            "moduleJars": sorted(name for name in names if name.endswith(".jar") and "/modules/" in name),
            "pluginDirectories": sorted({name.split("/")[1] for name in names if name.startswith("plugins/") and len(name.split("/")) > 2}),
            "runtimeRelease": runtime,
        }
    data = json.loads(metadata.read_text())
    result["enabledPlugins"] = data["plugins"]
    result["contentModules"] = sorted(item["name"] for item in data["layout"] if item["kind"] in ("productModuleV2", "moduleV2"))
    return result


parser = argparse.ArgumentParser()
parser.add_argument("baseline", type=Path)
parser.add_argument("current", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--baseline-modules", required=True, type=Path)
parser.add_argument("--current-modules", required=True, type=Path)
args = parser.parse_args()
before = inventory(args.baseline, args.baseline_modules)
after = inventory(args.current, args.current_modules)
report = {
    "interpretation": "ZIP module JARs and content descriptors of enabled plugins. The upstream lister enumerates plugin.contentModules without filtering each module's runtime enablement. Not JPS compile roots or classes actually loaded in a user session.",
    "baseline": before,
    "current": after,
    "savedArchiveBytes": before["archiveBytes"] - after["archiveBytes"],
    "removedModuleJars": sorted(set(before["moduleJars"]) - set(after["moduleJars"])),
    "addedModuleJars": sorted(set(after["moduleJars"]) - set(before["moduleJars"])),
    "removedContentModules": sorted(set(before["contentModules"]) - set(after["contentModules"])),
    "addedContentModules": sorted(set(after["contentModules"]) - set(before["contentModules"])),
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"baselineBytes": before["archiveBytes"], "currentBytes": after["archiveBytes"], "savedBytes": report["savedArchiveBytes"], "removedModuleJars": report["removedModuleJars"]}, indent=2))
