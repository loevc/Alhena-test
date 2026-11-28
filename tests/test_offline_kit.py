import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("offline_kit", Path(__file__).resolve().parents[1] / "tools/offline-kit.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class OfflineKitTests(unittest.TestCase):
    def fixture(self, root):
        (root / "build-support").mkdir()
        (root / "product/build").mkdir(parents=True)
        (root / "product/build/Target.kt").write_text("source\n")
        (root / "product/__pycache__").mkdir()
        (root / "product/__pycache__/bad.pyc").write_bytes(b"cache")
        (root / kit.SOURCE_MANIFEST).write_text(json.dumps({
            "include": ["product", "build-support"], "excludeDirectoryNames": ["__pycache__"],
            "excludePaths": [], "excludeSuffixes": [".pyc"]}))
        (root / kit.KIT_LOCK).write_text("{}")

    def test_submission_keeps_build_sources_and_excludes_generated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            files = kit.source_files(root)
            self.assertIn("product/build/Target.kt", files)
            self.assertNotIn(kit.KIT_LOCK, files)  # Avoid circular archive hashes.
            self.assertFalse(any("__pycache__" in name for name in files))

    def test_unsafe_archive_paths_are_rejected(self):
        for name in ("../outside", "/absolute", "C:/drive", "cache\\outside", "a/../b", "a//b", "a./file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                kit.safe_name(name)
        self.assertEqual(kit.safe_name("product/build/Target.kt").as_posix(), "product/build/Target.kt")

    def make_archive(self, root):
        self.fixture(root)
        files = kit.source_files(root)
        inputs = {name: root / name for name in files}
        archive = root / "snapshot.zip"
        with patch.object(kit, "collect", return_value=({"commit": "a" * 40}, inputs, files)):
            kit.export(root, archive, root / "unused")
        return archive, kit.read(root / kit.KIT_LOCK)

    def test_roundtrip_manifest_and_corruption_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, lock = self.make_archive(root)
            manifest = kit.verify(archive, lock)
            self.assertEqual(manifest["upstreamCommit"], "a" * 40)
            with archive.open("ab") as output:
                output.write(b"corrupt")
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                kit.verify(archive, lock)

    def test_payload_hash_checked_even_if_outer_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, lock = self.make_archive(root)
            changed = root / "changed.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(changed, "w") as output:
                for name in source.namelist():
                    data = source.read(name)
                    output.writestr(name, b"broken\n" if name.endswith("Target.kt") else data)
            lock.update(archiveSize=changed.stat().st_size, archiveSha256=kit.digest(changed))
            with self.assertRaisesRegex(RuntimeError, "Size mismatch|Payload SHA-256 mismatch"):
                kit.verify(changed, lock)

    def test_export_will_not_replace_an_existing_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "backup.zip"
            archive.write_bytes(b"original")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                kit.export(root, archive, root)
            self.assertEqual(archive.read_bytes(), b"original")

    @unittest.skipUnless(os.name == "nt", "Windows restore protocol")
    def test_restore_into_checkout_rejects_extra_source_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, lock = self.make_archive(root)
            (root / ".git").mkdir()
            (root / "product/build/Unrecorded.kt").write_text("new source")
            with self.assertRaisesRegex(RuntimeError, "source file set differs"):
                kit.restore(archive, lock, root, into_checkout=True)

    def test_unmanaged_upstream_edits_are_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "patches").mkdir()
            (root / "patches/upstream.json").write_text("[]")
            with patch.object(kit, "git", return_value="plugins/unrecorded.kt\0"):
                with self.assertRaisesRegex(RuntimeError, "Uncaptured upstream edits"):
                    kit.ensure_exportable(root, root / "source")

    def test_prepared_local_edits_are_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "patches").mkdir()
            (root / "patches/upstream.json").write_text("[]")
            source = root / "source"
            source.mkdir()
            (source / "Some.java").write_text("local edit")
            (source / ".alhena-overlay.json").write_text(json.dumps({"Some.java": "0" * 64}))
            with patch.object(kit, "git", return_value=""):
                with self.assertRaisesRegex(RuntimeError, "Locally edited prepared file"):
                    kit.ensure_exportable(root, source)


if __name__ == "__main__":
    unittest.main()
