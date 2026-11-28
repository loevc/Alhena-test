import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("desktop_gate", Path(__file__).resolve().parents[1] / "tools/desktop-gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class DesktopGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        archive = self.folder / "candidate.zip"
        archive.write_bytes(b"candidate")
        self.report = {"status": "passed", "archive": str(archive), "archiveSha256": gate.digest(archive),
                       "cases": {}, "sourceSha256": {}}
        for name in gate.CASES:
            result = {"status": "passed", "archiveSha256": self.report["archiveSha256"], "checks": ["actual check"],
                      "evidence": name, "commandLineMode": True, "existingProject": True,
                      "nativeSelection": True, "repositorySwitching": True,
                      "powerShellVersion": "5.1.0" if name == "cli-ps51" else "7.5.0"}
            gate.save(self.folder / (name + ".json"), result)
            self.rehash(name)

    def rehash(self, name):
        path = self.folder / (name + ".json")
        self.report["cases"][name] = {"resultSha256": gate.digest(path), "originalEvidence": name}

    def test_complete_evidence(self):
        gate.validate(self.report, self.folder)

    def test_missing_case_rejected(self):
        del self.report["cases"]["advanced"]
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            gate.validate(self.report, self.folder)

    def test_changed_evidence_rejected(self):
        (self.folder / "advanced.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            gate.validate(self.report, self.folder)

    def test_mixed_archive_rejected_even_with_updated_evidence_hash(self):
        path = self.folder / "advanced.json"
        result = gate.read(path)
        result["archiveSha256"] = "other-build"
        gate.save(path, result)
        self.rehash("advanced")
        with self.assertRaisesRegex(ValueError, "mixed archives"):
            gate.validate(self.report, self.folder)

    def test_archive_replacement_rejected(self):
        Path(self.report["archive"]).write_bytes(b"replacement")
        with self.assertRaisesRegex(ValueError, "Archive changed"):
            gate.validate(self.report, self.folder)

    def test_source_changes_rejected(self):
        self.report["sourceSha256"] = {"run.ps1": "0" * 64}
        with self.assertRaisesRegex(ValueError, "Source changed"):
            gate.validate(self.report, self.folder)

    def test_wrong_shell_and_missing_switch_rejected(self):
        for name, field, value in (("cli-ps51", "powerShellVersion", "7.5.0"),
                                   ("native-switch", "repositorySwitching", False)):
            with self.subTest(case=name):
                original_report = copy.deepcopy(self.report)
                path = self.folder / (name + ".json")
                original = gate.read(path)
                result = dict(original, **{field: value})
                gate.save(path, result)
                self.rehash(name)
                with self.assertRaises(ValueError):
                    gate.validate(self.report, self.folder)
                gate.save(path, original)
                self.report = original_report
