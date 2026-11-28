"""Capture/verify IDE metadata in isolated acceptance fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(repository):
    result = {}
    for directory, subdirs, files in os.walk(repository, followlinks=False):
        subdirs[:] = [name for name in subdirs if name.lower() != ".git"]
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(repository)
            if not any(part.lower() == ".idea" for part in relative.parts) and path.suffix.lower() != ".iml":
                continue
            if path.is_symlink():
                raise ValueError("Unexpected metadata symlink: " + str(relative))
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "verify"))
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    snapshot = args.snapshot.resolve()
    if not repository.is_relative_to(ROOT / "out/fixtures") or not (repository / ".git").exists():
        raise ValueError("Repository must be an isolated fixture")
    if not snapshot.is_relative_to(ROOT / "out") or snapshot.is_relative_to(repository):
        raise ValueError("Snapshot must be outside the fixture, within out")
    files = collect(repository)
    if args.mode == "capture":
        if snapshot.exists():
            raise ValueError("Refuse to overwrite an existing baseline")
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps({"repository": str(repository), "files": files}, indent=2) + "\n", encoding="utf-8")
    else:
        expected = json.loads(snapshot.read_text(encoding="utf-8"))
        if expected["repository"] != str(repository):
            raise ValueError("Snapshot belongs to another repository")
        changed = sorted(key for key in set(files) | set(expected["files"]) if files.get(key) != expected["files"].get(key))
        if changed:
            raise ValueError("IDE metadata changed: " + ", ".join(changed[:20]))
    print(json.dumps({"status": "captured" if args.mode == "capture" else "unchanged", "files": len(files)}))


if __name__ == "__main__":
    main()
