"""Prepare a pinned IntelliJ checkout and report its production module dependencies.

No third-party Python packages. The dependency report is a static JPS over-approximation,
not a claim that every reachable module is loaded or packed in the final distribution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
SOURCE = ROOT / LOCK["checkout"]
PATCH_MANIFEST = ROOT / "patches/upstream.json"


def patched_bytes(original, current, patch):
    key = patch["path"]
    if hashlib.sha256(original).hexdigest() != patch["sha256"]:
        raise RuntimeError(f"Upstream patch base mismatch: {key}")
    old, new = patch["old"].encode(), patch["new"].encode()
    if original.count(old) != 1:
        raise RuntimeError(f"Upstream patch must match exactly once: {key}")
    data = original.replace(old, new, 1)
    if current not in (original, data):
        raise RuntimeError(f"Refusing to overwrite locally edited patched file: {key}")
    return data


def git(*args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={SOURCE.as_posix()}", "-C", str(SOURCE), *args],
        text=True, encoding="utf-8",
    ).strip()


def verify_pin():
    actual = git("rev-parse", "HEAD")
    if actual != LOCK["commit"]:
        raise RuntimeError(f"Upstream revision mismatch: {actual}; expected {LOCK['commit']}")


def validate_version(major, minor, build_number):
    branch = build_number.split(".")[0]
    if (major + minor).removeprefix("20")[:len(branch)] != branch:
        raise RuntimeError(f"Product version {major}.{minor} does not match upstream build {build_number}")


def version_metadata(version):
    # full is also consumed by the platform About dialog and artifact naming.
    # Keep it literal, filename-safe and independent of the compatibility fields.
    full = version.get("full", "")
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?", full):
        raise RuntimeError("A literal filename-safe Alhena semantic version is required")
    return {"schemaVersion": 1, "product": "Alhena", "productVersion": full,
            "platformVersion": LOCK["applicationVersion"], "platformTag": LOCK["tag"],
            "platformCommit": LOCK["commit"], "runtimeBuild": LOCK["runtime"]["build"]}


def write_icon(path):
    """Original geometric ICO, with all eight images required by the launcher."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    sizes = (16, 20, 24, 32, 40, 48, 64, 256)
    images, entries = [], []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        rows = bytearray()
        for y in range(size):
            rows.append(0)
            for x in range(size):
                px, py = (x + .5) * 64 / size, (y + .5) * 64 / size
                in_a = 12 <= py < 52 and abs(px - 32) < (py - 8) * .45
                hole = 24 <= py < 38 and abs(px - 32) < (py - 19) * .25
                gap = py >= 43 and abs(px - 32) < (py - 25) * .22
                rows.extend((183, 160, 248, 255) if in_a and not hole and not gap else (37, 38, 43, 255))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", size, size, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
        entries.append(struct.pack("<4B2H2I", size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
        images.append(png)
        offset += len(png)
    path.write_bytes(struct.pack("<3H", 0, 1, len(sizes)) + b"".join(entries) + b"".join(images))


def prepare():
    verify_pin()
    version = ET.parse(ROOT / "product/resources/idea/AlhenaApplicationInfo.xml").getroot().find("{*}version")
    validate_version(version.attrib["major"], version.attrib["minor"], (SOURCE / "build.txt").read_text().strip())
    managed_file = SOURCE / ".alhena-overlay.json"
    managed = json.loads(managed_file.read_text()) if managed_file.exists() else {}
    files = {}
    for source in (ROOT / "product").rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(ROOT / "product")
        if relative.parts[0] in ("build", "platform-build"):
            base = "build/src/alhena" if relative.parts[0] == "build" else "platform/build-scripts/src/alhena"
            destination = SOURCE / base / Path(*relative.parts[1:])
        else:
            destination = SOURCE / "alhena" / relative
        key = destination.relative_to(SOURCE).as_posix()
        data = source.read_bytes()
        if destination.exists():
            current = destination.read_bytes()
            if current != data and hashlib.sha256(current).hexdigest() != managed.get(key):
                raise RuntimeError(f"Refusing to overwrite locally edited overlay file: {key}")
        files[key] = (destination, data)
    # One policy controls both registered content modules and packed classes.
    policy = ROOT / "product/resources/alhena-excluded-modules.txt"
    excluded = {line.strip() for line in policy.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")}
    module_xml = ET.parse(SOURCE / "platform/platform-resources/src/META-INF/essential-modules.xml")
    content = module_xml.getroot().find("content")
    removed = set()
    for module in list(content):
        if module.get("name") in excluded:
            removed.add(module.get("name"))
            content.remove(module)
    if removed != excluded:
        raise RuntimeError(f"Excluded modules missing from pinned descriptor: {sorted(excluded - removed)}")
    destination = SOURCE / "alhena/resources/META-INF/AlhenaModules.xml"
    key = destination.relative_to(SOURCE).as_posix()
    data = b"<!-- Generated from pinned essential-modules.xml; see alhena-excluded-modules.txt. -->\n" + ET.tostring(module_xml.getroot(), encoding="utf-8")
    if destination.exists() and destination.read_bytes() != data and hashlib.sha256(destination.read_bytes()).hexdigest() != managed.get(key):
        raise RuntimeError(f"Refusing to overwrite locally edited overlay file: {key}")
    files[key] = (destination, data)
    destination = SOURCE / "alhena/resources/alhena-version.json"
    key = destination.relative_to(SOURCE).as_posix()
    data = (json.dumps(version_metadata(version.attrib), indent=2) + "\n").encode("utf-8")
    if destination.exists() and destination.read_bytes() != data and hashlib.sha256(destination.read_bytes()).hexdigest() != managed.get(key):
        raise RuntimeError(f"Refusing to overwrite locally edited overlay file: {key}")
    files[key] = (destination, data)
    # Pinned compatibility patches are explicit and reject upstream/local drift.
    for patch in json.loads(PATCH_MANIFEST.read_text(encoding="utf-8")) if PATCH_MANIFEST.exists() else []:
        destination = SOURCE / patch["path"]
        key = destination.relative_to(SOURCE).as_posix()
        current = destination.read_bytes()
        original = subprocess.check_output(
            ["git", "-c", f"safe.directory={SOURCE.as_posix()}", "-C", str(SOURCE), "show", f"HEAD:{key}"]
        )
        files[key] = (destination, patched_bytes(original, current, patch))
    # Validate every destination before applying any file updates.
    for key, (destination, data) in files.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        managed[key] = hashlib.sha256(data).hexdigest()
    write_icon(SOURCE / "alhena/resources/alhena.ico")

    module_file = SOURCE / ".idea/modules.xml"
    tree = ET.parse(module_file)
    modules = tree.find("./component[@name='ProjectModuleManager']/modules")
    if modules is None:
        raise RuntimeError("Unsupported upstream modules.xml format")
    module_path = "$PROJECT_DIR$/alhena/alhena.product.iml"
    if not any(m.get("filepath") == module_path for m in modules):
        ET.SubElement(modules, "module", {"fileurl": "file://" + module_path, "filepath": module_path})
        tree.write(module_file, encoding="UTF-8", xml_declaration=True)
    managed_file.write_text(json.dumps(managed, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {LOCK['tag']} @ {LOCK['commit']}; overlay files: {len(files)}")


def parse_module(path):
    xml = ET.parse(path).getroot()
    dependencies = []
    libraries = set()
    for entry in xml.findall("./component[@name='NewModuleRootManager']/orderEntry"):
        if entry.get("scope", "COMPILE") == "TEST":
            continue
        if entry.get("type") == "module":
            dependencies.append({"name": entry.attrib["module-name"], "scope": entry.get("scope", "COMPILE")})
        if entry.get("type") == "library":
            libraries.add(entry.attrib["name"])
    roots = []
    for folder in xml.findall("./component[@name='NewModuleRootManager']/content/sourceFolder"):
        if folder.get("isTestSource") == "true" or "test" in folder.get("type", "").lower():
            continue
        url = folder.get("url", "")
        if url.startswith("file://$MODULE_DIR$"):
            roots.append(str(path.parent / url.removeprefix("file://$MODULE_DIR$").lstrip("/")))
    return {"dependencies": dependencies, "libraries": sorted(libraries), "resourceRoots": roots}


def closure(modules, seeds):
    visited, missing = set(), set()
    pending = list(seeds)
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        if name not in modules:
            missing.add(name)
            continue
        visited.add(name)
        pending.extend(d["name"] for d in modules[name]["dependencies"])
    return sorted(visited), sorted(missing)


def descriptors(modules):
    """Inventory XIncludes/content IDs; deliberately do not simulate plugin loading."""
    roots = [Path(root) for module in modules.values() for root in module["resourceRoots"]]
    pending = [SOURCE / "alhena/resources/META-INF/AlhenaPlugin.xml",
               SOURCE / "plugins/git4idea/resources/META-INF/plugin.xml"]
    seen, content, unresolved, parse_errors = set(), set(), [], []
    xi = "{http://www.w3.org/2001/XInclude}"
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            xml = ET.parse(path)
        except (ET.ParseError, OSError) as error:
            parse_errors.append({"file": str(path.relative_to(SOURCE)), "error": str(error)})
            continue
        content.update(node.attrib["name"] for node in xml.findall(".//content/module") if "name" in node.attrib)
        for include in xml.findall(".//" + xi + "include"):
            href = include.get("href", "")
            if not href or "://" in href:
                continue
            candidates = ([path.parent / href] if not href.startswith("/") else [])
            candidates += [root / href.lstrip("/") for root in roots]
            found = next((candidate for candidate in candidates if candidate.is_file()), None)
            if found is not None:
                pending.append(found)
            else:
                unresolved.append({"from": path.relative_to(SOURCE).as_posix(), "href": href,
                                   "optional": include.find(xi + "fallback") is not None})
    return {"files": sorted(path.relative_to(SOURCE).as_posix() for path in seen),
            "contentModuleIds": sorted(content), "unresolvedIncludes": unresolved,
            "parseErrors": parse_errors,
            "limitations": "Includes searched across all project source roots, not actual classloader order. XPointer/loading modes and module dependencies are not simulated; slash content IDs are descriptor IDs, not JPS names."}


def audit():
    verify_pin()
    modules, missing_files = {}, []
    for entry in ET.parse(SOURCE / ".idea/modules.xml").findall(".//modules/module"):
        raw = entry.attrib["filepath"]
        path = Path(raw.replace("$PROJECT_DIR$", str(SOURCE)))
        if "$" in str(path) or not path.is_file():
            missing_files.append(raw)
            continue
        item = parse_module(path)
        item["path"] = path.relative_to(SOURCE).as_posix()
        modules[path.stem] = item
    seeds = ["alhena.product", "intellij.platform.starter", "intellij.vcs.git",
             "intellij.platform.vcs.log.impl", "intellij.platform.diff.impl"]
    reached, missing = closure(modules, seeds)
    plugin = ET.parse(ROOT / "product/resources/META-INF/AlhenaPlugin.xml")
    includes = [e.attrib["href"] for e in plugin.findall("{http://www.w3.org/2001/XInclude}include")]
    report = {
        "upstream": LOCK,
        "interpretation": "Non-TEST JPS dependency reachability, including PROVIDED. Not a runtime or packaging inventory. XML content modules, XIncludes, services and reflective dependencies require separate runtime validation.",
        "indexedModules": len(modules), "seeds": seeds,
        "reachableCount": len(reached), "unresolvedDependencies": missing,
        "unavailableModuleFiles": missing_files,
        "coreDescriptorIncludes": includes,
        "modules": {name: modules[name] for name in reached},
        "descriptorInventory": descriptors(modules),
    }
    output = ROOT / "out/reports"
    output.mkdir(parents=True, exist_ok=True)
    (output / "dependencies.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Alhena JPS dependency audit", "", f"Upstream: `{LOCK['tag']}` / `{LOCK['commit']}`", "",
             report["interpretation"], "", f"Indexed: {len(modules)}; reachable: {len(reached)}; unresolved: {len(missing)}; unavailable module files: {len(missing_files)}.", "",
             "## Reachable production dependencies", "", "| Module | Source |", "| --- | --- |"]
    lines.extend(f"| `{name}` | `{modules[name]['path']}` |" for name in reached)
    lines += ["", "## Unresolved dependencies", ""] + [f"- `{name}`" for name in missing]
    inventory = report["descriptorInventory"]
    lines += ["", "## Descriptor inventory (not a loader simulation)", "", inventory["limitations"], "",
              f"XML files: {len(inventory['files'])}; content module IDs: {len(inventory['contentModuleIds'])}; unresolved includes: {len(inventory['unresolvedIncludes'])}.", ""]
    lines.extend(f"- `{name}`" for name in inventory["contentModuleIds"])
    (output / "dependencies.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Indexed {len(modules)} modules; {len(reached)} reachable; {len(missing)} unresolved; {len(missing_files)} unavailable module files")
    print(output / "dependencies.md")
    print(f"Descriptors: {len(inventory['files'])} XML files; {len(inventory['contentModuleIds'])} content IDs; {len(inventory['unresolvedIncludes'])} unresolved XIncludes")
    if missing:
        raise RuntimeError("Dependency audit is incomplete; inspect dependencies.json before compiling")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "audit"])
    args = parser.parse_args()
    {"prepare": prepare, "audit": audit}[args.action]()
