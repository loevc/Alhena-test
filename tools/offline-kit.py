"""Capture/restore a Windows x64 source-and-dependency kit without machine paths.

Uses only Python stdlib and Git. The kit deliberately contains no compiled Alhena
classes, JPS incremental state, personal Maven settings, Git config or credentials.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = "build-support/source-manifest.json"
KIT_LOCK = "build-support/offline.lock.json"
VALIDATION = "build-support/offline-validation.json"
MANIFEST = "offline-manifest.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_path(path):
    """Python file APIs need extended paths on Windows without global OS tweaks."""
    if os.name != "nt":
        return path
    value = str(path.absolute())
    if value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest_stream(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return digest_stream(stream)


def recipe_bytes(path):
    data = path.read_bytes()
    # Match this repository's .gitattributes, independently of the exporting
    # machine's pre-existing CRLF working tree. Binary assets stay untouched.
    if path.suffix.lower() not in (".png", ".ico", ".zip", ".jar", ".gz", ".pack") and b"\0" not in data[:8000]:
        data = data.replace(b"\r\n", b"\n")
    return data


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute() or
            any(part in ("", ".", "..") or part.endswith((".", " ")) for part in name.split("/"))):
        raise ValueError(f"Unsafe archive path: {name}")
    return path


def source_files(root):
    policy = read(root / SOURCE_MANIFEST)
    found = set()
    for name in policy["include"]:
        safe_name(name)
        path = root / name
        if not path.exists():
            raise RuntimeError(f"Missing submission input: {name}")
        for item in ([path] if path.is_file() else path.rglob("*")):
            relative = item.relative_to(root)
            key = relative.as_posix()
            if key in (KIT_LOCK, VALIDATION) or any(part in policy["excludeDirectoryNames"] for part in relative.parts):
                continue
            if any(key == prefix or key.startswith(prefix + "/") for prefix in policy["excludePaths"]):
                continue
            if item.suffix in policy["excludeSuffixes"]:
                continue
            if item.is_symlink():
                raise RuntimeError(f"Source symlinks are not supported: {key}")
            if item.is_file():
                found.add(key)
    return sorted(found)


def git(source, *args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={source.as_posix()}", "-c", "core.longpaths=true",
         "-C", str(source), *args], encoding="utf-8").strip()


def fingerprint(entries):
    return hashlib.sha256(json_bytes(sorted(entries, key=lambda entry: entry["path"]))).hexdigest()


def ensure_exportable(root, source):
    """Never silently drop edits from the ignored upstream working tree."""
    patches = read(root / "patches/upstream.json")
    allowed = {".idea/modules.xml"} | {item["path"] for item in patches}
    changed = set(filter(None, git(source, "diff", "HEAD", "--name-only", "-z").split("\0")))
    if changed - allowed:
        raise RuntimeError(f"Uncaptured upstream edits; move them into product/ or patches/: {sorted(changed - allowed)}")
    managed_file = source / ".alhena-overlay.json"
    if not managed_file.is_file():
        raise RuntimeError("Run build.ps1 -Action Prepare before exporting")
    managed = read(managed_file)
    for name, expected in managed.items():
        path = file_path(source / name)
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError(f"Locally edited prepared file would be lost on recovery: {name}")
    untracked = set(filter(None, git(source, "ls-files", "--others", "--exclude-standard", "-z").split("\0")))
    unexpected = untracked - set(managed) - {".alhena-overlay.json", "alhena/resources/alhena.ico"}
    if unexpected:
        raise RuntimeError(f"Uncaptured upstream files; move them into product/ or patches/: {sorted(unexpected)}")
    actual = ET.parse(source / ".idea/modules.xml").getroot()
    modules = actual.find("./component[@name='ProjectModuleManager']/modules")
    own = [item for item in modules if item.get("filepath") == "$PROJECT_DIR$/alhena/alhena.product.iml"]
    if len(own) != 1:
        raise RuntimeError("Prepared Alhena module registration is missing or duplicated")
    modules.remove(own[0])
    original = ET.fromstring(git(source, "show", "HEAD:.idea/modules.xml"))
    if ET.tostring(actual) != ET.tostring(original):
        raise RuntimeError("Uncaptured upstream modules.xml edits; only generated Alhena registration is supported")


def collect(root, maven):
    lock = read(root / "upstream.lock.json")
    safe_name(lock["checkout"])
    source = root / lock["checkout"]
    if git(source, "rev-parse", "HEAD") != lock["commit"]:
        raise RuntimeError("Upstream commit differs from upstream.lock.json")
    ensure_exportable(root, source)
    # A partial clone may still lack blobs, even if an earlier build passed.
    objects = git(source, "rev-list", "--objects", "--missing=print", "HEAD")
    if any(line.startswith("?") for line in objects.splitlines()):
        raise RuntimeError("Upstream has missing Git objects; hydrate the pinned tree before export")
    metadata = source / ".git"
    if not metadata.is_dir() or (metadata / "objects/info/alternates").exists():
        raise RuntimeError("Export requires a standalone checkout without object alternates")
    inputs = {name: root / name for name in source_files(root)}
    recipe_names = sorted(inputs)
    # Carry the complete pinned object database, not the huge checked-out tree.
    # Exclude promisor markers and machine/user-specific Git metadata.
    for path in (metadata / "objects").rglob("*"):
        relative = path.relative_to(metadata / "objects")
        if path.is_file() and (path.suffix in (".pack", ".idx") or
                               (len(relative.parts) == 2 and re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{38}", relative.as_posix()))):
            inputs[f'{lock["checkout"]}/.git/objects/{relative.as_posix()}'] = path
    if (metadata / "shallow").exists():
        inputs[f'{lock["checkout"]}/.git/shallow'] = metadata / "shallow"
    download = source / "build/download"
    for path in download.iterdir():
        # Re-extract at the destination: upstream extraction cache names contain
        # absolute-path hashes. Never transport partial downloads or flag files.
        if path.is_file() and path.name.endswith((".jar", ".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.zst")):
            inputs[f'{lock["checkout"]}/build/download/{path.name}'] = path
    bootstrap = file_path(root / ".cache/bootstrap")
    maven = file_path(maven)
    if not bootstrap.is_dir() or not any(bootstrap.rglob("javac.exe")):
        raise RuntimeError("Missing downloaded bootstrap JDK")
    if not maven.is_dir() or not any(maven.rglob("maven-resolver-ant-tasks-*-uber.jar")):
        raise RuntimeError("Maven repository does not contain bootstrap resolver dependencies")
    for base, prefix in ((bootstrap, ".cache/bootstrap"), (maven, ".cache/offline-home/.m2/repository")):
        for path in base.rglob("*"):
            if path.is_symlink():
                raise RuntimeError(f"Cache symlinks are not supported: {path}")
            if path.is_file() and not path.name.endswith((".lastUpdated", ".part", ".lock", ".tmp")):
                inputs[f"{prefix}/{path.relative_to(base).as_posix()}"] = path
    return lock, inputs, recipe_names


def export(root, archive, maven):
    if archive.exists():
        raise RuntimeError("Archive already exists; choose a new name rather than replacing a backup")
    lock, inputs, recipe_names = collect(root, maven)
    archive.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    print(f"Exporting {len(inputs)} files to {archive}", flush=True)
    # Most bytes are already compressed Git packs/JARs/tarballs. Store them once
    # instead of spending CPU recompressing several GiB during every backup.
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
        for number, (name, path) in enumerate(sorted(inputs.items()), 1):
            safe_name(name)
            hasher = hashlib.sha256()
            size = 0
            content = io.BytesIO(recipe_bytes(path)) if name in recipe_names else path.open("rb")
            with content as source, output.open(name, "w", force_zip64=True) as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    hasher.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
            entries.append({"path": name, "size": size, "sha256": hasher.hexdigest()})
            if number % 2000 == 0:
                print(f"  {number}/{len(inputs)} files", flush=True)
        recipe = [entry for entry in entries if entry["path"] in recipe_names]
        manifest = {"schemaVersion": 1, "platform": "windows-x64", "upstreamCommit": lock["commit"],
                    "recipeFingerprint": fingerprint(recipe), "recipeFiles": recipe_names, "files": entries}
        manifest_bytes = json_bytes(manifest)
        output.writestr(MANIFEST, manifest_bytes)
    kit_lock = {"schemaVersion": 1, "platform": "windows-x64",
                "createdAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "archiveName": archive.name, "archiveSize": archive.stat().st_size,
                "archiveSha256": digest(archive), "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "upstreamCommit": lock["commit"], "recipeFingerprint": manifest["recipeFingerprint"],
                "payloadFiles": len(entries), "payloadBytes": sum(entry["size"] for entry in entries)}
    (root / KIT_LOCK).write_bytes(json_bytes(kit_lock))
    archive.with_suffix(archive.suffix + ".json").write_bytes(json_bytes(kit_lock))
    print(json.dumps(kit_lock, indent=2), flush=True)


def verify(archive, kit_lock):
    if archive.stat().st_size != kit_lock["archiveSize"] or digest(archive) != kit_lock["archiveSha256"]:
        raise RuntimeError("Offline archive size/SHA-256 mismatch")
    with zipfile.ZipFile(archive) as source:
        data = source.read(MANIFEST)
        if hashlib.sha256(data).hexdigest() != kit_lock["manifestSha256"]:
            raise RuntimeError("Offline manifest SHA-256 mismatch")
        manifest = json.loads(data)
        if manifest["platform"] != "windows-x64" or manifest["upstreamCommit"] != kit_lock["upstreamCommit"]:
            raise RuntimeError("Unsupported platform or mismatched upstream commit")
        names = [info.filename for info in source.infolist()]
        for name in names:
            safe_name(name)
        entries = manifest["files"]
        if len(names) != len(set(name.casefold() for name in names)) or set(names) != {entry["path"] for entry in entries} | {MANIFEST}:
            raise RuntimeError("Duplicate or unlisted archive member")
        for entry in entries:
            if source.getinfo(entry["path"]).file_size != entry["size"]:
                raise RuntimeError(f'Size mismatch: {entry["path"]}')
            with source.open(entry["path"]) as stream:
                if digest_stream(stream) != entry["sha256"]:
                    raise RuntimeError(f'Payload SHA-256 mismatch: {entry["path"]}')
        recipe = [entry for entry in entries if entry["path"] in manifest["recipeFiles"]]
        if fingerprint(recipe) != kit_lock["recipeFingerprint"]:
            raise RuntimeError("Recipe fingerprint mismatch")
    return manifest


def restore(archive, kit_lock, destination, into_checkout=False):
    if os.name != "nt":
        raise RuntimeError("This kit builds Windows x64 only")
    if destination.exists() and not into_checkout:
        raise RuntimeError("Restore requires a new, nonexistent destination directory")
    manifest = verify(archive, kit_lock)  # Check every byte before writing any destination file.
    if into_checkout:
        if not (destination / ".git").exists():
            raise RuntimeError("--into-checkout requires an existing Alhena Git checkout")
        if source_files(destination) != manifest["recipeFiles"]:
            raise RuntimeError("Checkout source file set differs from kit recipe")
        for entry in manifest["files"]:
            if entry["path"] in manifest["recipeFiles"]:
                path = destination / entry["path"]
                if not path.is_file() or hashlib.sha256(recipe_bytes(path)).hexdigest() != entry["sha256"]:
                    raise RuntimeError(f'Checkout differs from kit recipe: {entry["path"]}')
        upstream = read(destination / "upstream.lock.json")["checkout"]
        if any(path.exists() or path.is_symlink() for path in (destination / PurePosixPath(upstream).parts[0], destination / ".cache")):
            raise RuntimeError("Existing upstream/.cache will not be merged or replaced; use a fresh checkout")
    else:
        destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        for entry in manifest["files"]:
            if into_checkout and entry["path"] in manifest["recipeFiles"]:
                continue
            target = file_path(destination / entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry["path"]) as payload, target.open("xb") as output:
                shutil.copyfileobj(payload, output, 1024 * 1024)
    lock = read(destination / "upstream.lock.json")
    if lock["commit"] != manifest["upstreamCommit"]:
        raise RuntimeError("Restored source lock mismatch")
    source = destination / lock["checkout"]
    metadata = source / ".git"
    (metadata / "refs").mkdir(exist_ok=True)
    (metadata / "HEAD").write_text(lock["commit"] + "\n", encoding="ascii")
    (metadata / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = false\nsymlinks = false\nlongpaths = true\n", encoding="ascii")
    # This tree is brand-new; no user checkout, configuration or work is replaced.
    git(source, "reset", "--hard", "HEAD")
    if any(line.startswith("?") for line in git(source, "rev-list", "--objects", "--missing=print", "HEAD").splitlines()):
        raise RuntimeError("Restored Git objects are incomplete")
    (destination / KIT_LOCK).write_bytes(json_bytes(kit_lock))
    state = {"schemaVersion": 1, "archiveSha256": kit_lock["archiveSha256"],
             "upstreamCommit": lock["commit"], "recipeFingerprint": kit_lock["recipeFingerprint"]}
    (destination / ".cache/offline-state.json").write_bytes(json_bytes(state))
    print(f"Restored to {destination}. Run .\\build.ps1 -Action Package -Offline there.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="List explicit source files to commit")
    export_parser = sub.add_parser("export")
    export_parser.add_argument("--archive", type=Path, required=True)
    export_parser.add_argument("--maven-repository", type=Path, default=Path.home() / ".m2/repository")
    for action in ("verify", "restore"):
        command = sub.add_parser(action)
        command.add_argument("--archive", type=Path, required=True)
        command.add_argument("--lock", type=Path, default=ROOT / KIT_LOCK)
        if action == "restore":
            command.add_argument("--destination", type=Path, required=True)
            command.add_argument("--into-checkout", action="store_true")
    args = parser.parse_args()
    if args.action == "list":
        print("\n".join(source_files(ROOT) + [name for name in (KIT_LOCK, VALIDATION) if (ROOT / name).exists()]))
    elif args.action == "export":
        export(ROOT, args.archive.resolve(), args.maven_repository.resolve())
    elif args.action == "verify":
        manifest = verify(args.archive.resolve(), read(args.lock))
        print(f'Verified {len(manifest["files"])} payload files and source fingerprint')
    else:
        restore(args.archive.resolve(), read(args.lock), args.destination.resolve(), args.into_checkout)


if __name__ == "__main__":
    main()
