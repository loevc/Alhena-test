"""Test the guard and cleanup guarantees without network access or credentials."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("remote_fixture", Path(__file__).resolve().parents[1] / "tools/remote-fixture.py")
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class RemoteFixtureTests(unittest.TestCase):
    def test_source_repository_cannot_be_a_test_target(self):
        for origin in ("https://github.com/loevc/Alhena.git", "git@github.com:loevc/Alhena.git"):
            with self.subTest(origin=origin), patch.object(remote, "git", return_value=origin):
                with self.assertRaisesRegex(ValueError, "source repository"):
                    remote.validate_target("loevc/Alhena")

    def test_cleanup_destroys_private_key_even_if_revocation_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            folder = cache / "run"
            folder.mkdir()
            private = folder / "id_ed25519"
            private.write_text("test-only-placeholder")
            context = folder / "context.json"
            remote.save(context, {"repository": "loevc/Alhena-test", "runId": "run", "deployKeyId": 123,
                                  "privateKeyPath": str(private)})
            with patch.object(remote, "CACHE", cache), patch.object(remote, "validate_target"), \
                 patch.object(remote, "token", return_value="not-a-real-token"), \
                 patch.object(remote, "api", side_effect=OSError("network unavailable")):
                with self.assertRaises(OSError):
                    remote.cleanup(context)
            self.assertFalse(private.exists())
            saved = json.loads(context.read_text())
            self.assertEqual(saved["status"], "key-revocation-pending")
            self.assertEqual(saved["deployKeyId"], 123)
            self.assertNotIn("not-a-real-token", context.read_text())

    def test_cleanup_refuses_a_different_runs_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            folder = cache / "run"
            folder.mkdir()
            private = folder / "id_ed25519"
            private.write_text("test-only-placeholder")
            private.with_suffix(".pub").write_text("ssh-ed25519 owned-key")
            context = folder / "context.json"
            remote.save(context, {"repository": "loevc/Alhena-test", "runId": "run", "deployKeyId": 123,
                                  "privateKeyPath": str(private)})
            with patch.object(remote, "CACHE", cache), patch.object(remote, "validate_target"), \
                 patch.object(remote, "token", return_value="unused"), \
                 patch.object(remote, "api", return_value={"title": "Someone else's key", "key": "ssh-ed25519 other-key"}) as api:
                with self.assertRaisesRegex(ValueError, "not owned"):
                    remote.cleanup(context)
            self.assertEqual(api.call_count, 1)
            self.assertFalse(private.exists())


if __name__ == "__main__":
    unittest.main()
