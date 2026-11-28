import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("metadata_snapshot", Path(__file__).resolve().parents[1] / "tools/metadata-snapshot.py")
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class MetadataSnapshotTests(unittest.TestCase):
    def test_detects_added_modified_and_deleted_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".idea").mkdir()
            original = root / ".idea/workspace.xml"
            original.write_text("original")
            (root / "source.txt").write_text("not metadata")
            before = metadata.collect(root)
            self.assertEqual(set(before), {".idea/workspace.xml"})
            original.write_text("modified")
            self.assertNotEqual(metadata.collect(root), before)
            original.write_text("original")
            added = root / "unexpected.iml"
            added.write_text("module")
            self.assertNotEqual(metadata.collect(root), before)
            added.unlink()
            self.assertEqual(metadata.collect(root), before)
            original.unlink()
            self.assertNotEqual(metadata.collect(root), before)

    def test_uppercase_ide_directory_is_included(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".IDEA").mkdir()
            (root / ".IDEA/misc.xml").write_text("original")
            self.assertEqual(set(metadata.collect(root)), {".IDEA/misc.xml"})
