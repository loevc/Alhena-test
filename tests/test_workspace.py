import importlib.util
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("workspace", Path(__file__).resolve().parents[1] / "tools/workspace.py")
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


class DependencyTests(unittest.TestCase):
    def test_scopes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.iml"
            path.write_text('''<module><component name="NewModuleRootManager">
              <orderEntry type="module" module-name="runtime" scope="RUNTIME"/>
              <orderEntry type="module" module-name="compile"/>
              <orderEntry type="module" module-name="provided" scope="PROVIDED"/>
              <orderEntry type="module" module-name="test" scope="TEST"/>
              <orderEntry type="library" name="prod"/>
              <orderEntry type="library" name="test-lib" scope="TEST"/>
            </component></module>''', encoding="utf-8")
            parsed = workspace.parse_module(path)
            self.assertEqual([d["name"] for d in parsed["dependencies"]], ["runtime", "compile", "provided"])
            self.assertEqual(parsed["libraries"], ["prod"])

    def test_cycles_and_unresolved(self):
        modules = {"a": {"dependencies": [{"name": "b"}]},
                   "b": {"dependencies": [{"name": "a"}, {"name": "missing"}]}}
        self.assertEqual(workspace.closure(modules, ["a"]), (["a", "b"], ["missing"]))

    def test_prepare_is_idempotent_and_protects_local_edits(self):
        # Product versions are explicit fixture inputs, independent of the
        # repository's next release. Cover a development and a stable version.
        for product_version in ("0.1.1-dev", "2.3.4"):
            with self.subTest(product_version=product_version), tempfile.TemporaryDirectory() as temporary:
                fixture_root = Path(temporary) / "overlay"
                shutil.copytree(workspace.ROOT / "product", fixture_root / "product")
                app_info = fixture_root / "product/resources/idea/AlhenaApplicationInfo.xml"
                tree = ET.parse(app_info)
                tree.getroot().find("{*}version").set("full", product_version)
                tree.write(app_info, encoding="utf-8")
                source = Path(temporary) / "checkout"
                source.mkdir()
                (source / ".idea").mkdir()
                (source / "build.txt").write_text("252.28539.SNAPSHOT")
                descriptor = source / "platform/platform-resources/src/META-INF/essential-modules.xml"
                descriptor.parent.mkdir(parents=True)
                policy = (fixture_root / "product/resources/alhena-excluded-modules.txt").read_text().splitlines()
                excluded = [line.strip() for line in policy if line.strip() and not line.startswith("#")]
                descriptor.write_text('<idea-plugin><content><module name="keep"/>' + ''.join(f'<module name="{name}"/>' for name in excluded) + '</content></idea-plugin>')
                module_file = source / ".idea/modules.xml"
                module_file.write_text('<project><component name="ProjectModuleManager"><modules/></component></project>')
                with patch.object(workspace, "ROOT", fixture_root), patch.object(workspace, "SOURCE", source), patch.object(workspace, "git", return_value=workspace.LOCK["commit"]), patch.object(workspace, "PATCH_MANIFEST", source / "no-patches.json"):
                    workspace.prepare()
                    generated = source / "alhena/resources/META-INF/AlhenaModules.xml"
                    metadata = source / "alhena/resources/alhena-version.json"
                    self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["productVersion"], product_version)
                    self.assertIn(workspace.LOCK["commit"], metadata.read_text(encoding="utf-8"))
                    self.assertIn('name="keep"', generated.read_text())
                    for name in excluded:
                        self.assertNotIn(name, generated.read_text())
                    first = module_file.read_bytes()
                    workspace.prepare()
                    self.assertEqual(module_file.read_bytes(), first)
                    properties = source / "build/src/alhena/AlhenaProperties.kt"
                    edited = properties.read_bytes() + b"\n// local edit\n"
                    properties.write_bytes(edited)
                    with self.assertRaisesRegex(RuntimeError, "locally edited"):
                        workspace.prepare()
                    self.assertEqual(properties.read_bytes(), edited)


    def test_pin_mismatch_is_rejected(self):
        with patch.object(workspace, "git", return_value="unexpected-revision"):
            with self.assertRaisesRegex(RuntimeError, "revision mismatch"):
                workspace.verify_pin()

    def test_product_version_must_match_platform_build(self):
        workspace.validate_version("2025", "2", "252.28539.SNAPSHOT")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            workspace.validate_version("0", "1", "252.28539.SNAPSHOT")

    def test_independent_product_version_preserves_platform_identity(self):
        metadata = workspace.version_metadata({"full": "0.1.0-dev", "major": "2025", "minor": "2"})
        self.assertEqual(metadata["productVersion"], "0.1.0-dev")
        self.assertEqual(metadata["platformCommit"], workspace.LOCK["commit"])
        self.assertEqual(metadata["platformVersion"], workspace.LOCK["applicationVersion"])
        self.assertEqual(metadata["runtimeBuild"], workspace.LOCK["runtime"]["build"])
        for invalid in ("", "0.1", "{0}.{1}", "../1.0.0", "1.2.3 dev", "01.2.3"):
            with self.subTest(version=invalid), self.assertRaisesRegex(RuntimeError, "semantic version"):
                workspace.version_metadata({"full": invalid})

    def test_pinned_patch_rejects_drift_and_preserves_local_edits(self):
        original = b"before\n"
        patch_data = {"path": "source.kt", "sha256": hashlib.sha256(original).hexdigest(), "old": "before", "new": "after"}
        applied = workspace.patched_bytes(original, original, patch_data)
        self.assertEqual(applied, b"after\n")
        self.assertEqual(workspace.patched_bytes(original, applied, patch_data), applied)
        with self.assertRaisesRegex(RuntimeError, "base mismatch"):
            workspace.patched_bytes(b"updated upstream\n", original, patch_data)
        with self.assertRaisesRegex(RuntimeError, "locally edited"):
            workspace.patched_bytes(original, b"user edit\n", patch_data)

    def test_upgrade_patch_requires_exactly_one_match_even_with_matching_base_hash(self):
        for original in (b"before\nbefore\n", b"changed upstream API\n"):
            patch_data = {"path": "source.kt", "sha256": hashlib.sha256(original).hexdigest(), "old": "before", "new": "after"}
            with self.subTest(source=original), self.assertRaisesRegex(RuntimeError, "exactly once"):
                workspace.patched_bytes(original, original, patch_data)


if __name__ == "__main__":
    unittest.main()
