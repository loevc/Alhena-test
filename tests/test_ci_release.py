import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_release', ROOT / 'tools/ci-release.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
COMMIT = '1' * 40
TAG = 'v0.1.0-dev.2'


class FakeGitHub:
    def __init__(self, folder):
        self.folder = folder; self.release = None; self.writes = []
        self.tag_commit = COMMIT; self.corrupt_upload = False; self.fail_upload = False

    def request(self, path, method='GET', body=None, raw=None, missing_ok=False):
        if method != 'GET': self.writes.append((path, method))
        if '/commits/' in path: return {'sha': self.tag_commit}
        if '/releases?' in path: return [copy.deepcopy(self.release)] if self.release else []
        if '/releases/tags/' in path and self.release and self.release['draft']: return None
        if raw:
            if self.fail_upload: raise RuntimeError('Upload failed')
            p = Path(raw)
            self.release['assets'].append({'name': p.name, 'size': p.stat().st_size, 'state': 'uploaded',
                'digest': 'sha256:' + ('0' * 64 if self.corrupt_upload else r.digest(p))})
        elif method == 'POST':
            self.release = dict(body, id=1, assets=[], upload_url='https://uploads.github.com/upload{?name}', html_url='https://github.com/example/repo/releases/tag/' + TAG)
        elif method == 'PATCH': self.release.update(body)
        return copy.deepcopy(self.release)


class CiReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        app = self.root / 'product/resources/idea/AlhenaApplicationInfo.xml'; app.parent.mkdir(parents=True)
        app.write_text('<component><version full="0.1.0-dev" eap="true"/></component>', encoding='utf-8')
        (self.root / 'upstream.lock.json').write_text(json.dumps({'checkout': 'upstream', 'commit': '2' * 40}), encoding='utf-8')
        (self.root / 'upstream').mkdir()
        for name in ('LICENSE.txt', 'NOTICE.txt'): (self.root / 'upstream' / name).write_bytes(name.encode())
        self.archive = self.root / 'alhena-test.win.zip'
        self.entries = {n: b'placeholder' for n in r.REQUIRED}
        self.entries.update({'bin/alhena64.exe': b'MZlauncher', 'jbr/bin/java.exe': b'MZjava',
                             'product-info.json': json.dumps({'name': 'Alhena', 'productCode': 'AL', 'version': '0.1.0-dev', 'buildNumber': '252.28539'}).encode()})
        for name in ('LICENSE.txt', 'NOTICE.txt'): self.entries[name] = name.encode()
        self.write_zip()
        self.folder = self.root / 'assets'

    def write_zip(self):
        with zipfile.ZipFile(self.archive, 'w') as z:
            for n, b in self.entries.items(): z.writestr(n, b)

    def prepare(self):
        return r.prepare(self.archive, self.folder, COMMIT, TAG, root=self.root, runtime_check=False)

    def test_prepare_binds_exact_zip_and_eap(self):
        m = self.prepare(); self.assertTrue(m['prerelease'])
        self.assertEqual(m['assets'][0]['sha256'], r.digest(self.archive))
        self.assertIn(r.digest(self.archive), (self.folder / (self.archive.name + '.sha256')).read_text())
        self.assertEqual(m['desktopAcceptance'], 'not_run_on_hosted_runner')

    def test_wrong_version_or_unsafe_tag_rejected(self):
        for tag in ('v9.0.0', 'refs/tags/v0.1.0', 'v0.1.0/evil', 'bad'):
            with self.assertRaises(ValueError): r.validate_tag(tag, '0.1.0-dev')

    def test_missing_runtime_or_changed_notice_rejected(self):
        for name, value in [('jbr/bin/java.exe', None), ('NOTICE.txt', b'changed')]:
            entries = copy.deepcopy(self.entries)
            if value is None: self.entries.pop(name)
            else: self.entries[name] = value
            self.write_zip()
            with self.assertRaises(ValueError): self.prepare()
            self.entries = entries

    def test_path_traversal_in_zip_rejected(self):
        self.entries['jbr/../../escape'] = b'bad'; self.write_zip()
        with self.assertRaisesRegex(ValueError, 'Unsafe'): self.prepare()

    def test_artifact_tampering_prevents_api_writes(self):
        self.prepare(); (self.folder / self.archive.name).write_bytes(b'tampered')
        api = FakeGitHub(self.folder)
        with self.assertRaisesRegex(ValueError, 'asset changed'): r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertFalse(api.writes)

    def test_publish_uploads_then_publishes_and_is_idempotent(self):
        self.prepare(); api = FakeGitHub(self.folder)
        result = r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertEqual(result['status'], 'published_verified'); self.assertFalse(api.release['draft'])
        self.assertEqual(len(api.release['assets']), 4)
        count = len(api.writes); r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertEqual(len(api.writes), count)

    def test_moved_tag_prevents_publication(self):
        self.prepare(); api = FakeGitHub(self.folder); api.tag_commit = '3' * 40
        with self.assertRaisesRegex(ValueError, 'Remote tag'): r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertFalse(api.writes)

    def test_failed_upload_leaves_draft_and_can_resume(self):
        self.prepare(); api = FakeGitHub(self.folder); api.fail_upload = True
        with self.assertRaises(RuntimeError): r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertTrue(api.release['draft']); api.fail_upload = False
        r.publish(self.folder, 'example/repo', TAG, COMMIT, api); self.assertFalse(api.release['draft'])

    def test_wrong_server_digest_never_publishes(self):
        self.prepare(); api = FakeGitHub(self.folder); api.corrupt_upload = True
        with self.assertRaisesRegex(ValueError, 'asset differs'): r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertTrue(api.release['draft'])

    def test_existing_manual_release_is_preserved(self):
        self.prepare(); api = FakeGitHub(self.folder)
        api.release = {'body': 'manual release', 'tag_name': TAG, 'prerelease': True, 'draft': False}
        with self.assertRaisesRegex(ValueError, 'refusing to replace'): r.publish(self.folder, 'example/repo', TAG, COMMIT, api)
        self.assertFalse(api.writes)


if __name__ == '__main__': unittest.main()
