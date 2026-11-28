import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('association', ROOT / 'tools/verify-source-association.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class SourceAssociationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # A self-contained historical candidate: future source edits must not
        # break unit tests by comparing today's worktree to the old release.
        def write(path, value):
            p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(value).encode() if isinstance(value, dict) else value
            p.write_bytes(data)
            return {'originalSha256': v.sha(data), 'gitBlobSha256': v.sha(v.canonical_bytes(data, v.TEXT)), 'bytePolicy': v.TEXT}
        source = 'product/source.txt'
        source_record = write(source, b'example\r\n')
        source_record['testedCiBlobSha256'] = source_record['gitBlobSha256']
        candidate = {'archiveSha256': v.sha(b'candidate'), 'sourceCommit': '1' * 40,
                     'sourceChangesCommitted': True, 'sourceInputSha256': {source: source_record['originalSha256']}}
        ci = 'evidence/ci.json'
        records = {ci: write(ci, {'ciCanonicalSourceCommit': '2' * 40,
                                 'committedBlobSha256': {source: source_record['gitBlobSha256']}})}
        self.a = {'schemaVersion': 1, 'candidate': 'candidate.json', 'sourceCommit': '1' * 40,
                  'testedCiSourceCommit': '2' * 40, 'ciEvidence': ci,
                  'archiveSha256': candidate['archiveSha256'], 'candidateIdentitySha256': v.identity(candidate),
                  'sourceInputs': {source: source_record}, 'evidenceFiles': records, 'rawDigestLinks': [], 'gates': {}}
        write('candidate.json', candidate)
        for kind, cases in [('desktop', v.DESKTOP_CASES), ('remote', v.REMOTE_CASES)]:
            parent = 'evidence/' + kind + '/result.json'
            report = {'status': 'passed', 'archiveSha256': candidate['archiveSha256'],
                      'sourceSha256': candidate['sourceInputSha256'], 'temporaryKeyRevoked': True, 'cases': {}}
            for name in sorted(cases):
                child = 'evidence/' + kind + '/' + name + '.json'
                result = {'status': 'passed', 'archiveSha256': candidate['archiveSha256'], 'checks': ['verified'],
                          'evidence': name, 'repositorySwitching': True, 'nativeSelection': True,
                          'existingProject': True, 'commandLineMode': True,
                          'powerShellVersion': '5.1.1' if name == 'cli-ps51' else '7.1'}
                records[child] = write(child, result)
                report['cases'][name] = {'resultSha256': records[child]['originalSha256'], 'originalEvidence': name}
                self.a['rawDigestLinks'].append({'parent': parent, 'child': child, 'keys': ['cases', name, 'resultSha256']})
            records[parent] = write(parent, report)
            self.a['gates'][kind] = parent

    def test_source_only_checkout(self):
        result = v.verify(self.root, self.a)
        self.assertEqual(result['sourceFilesVerified'], 1)
        self.assertFalse(result['archiveVerified'])

    def test_lf_and_crlf_checkouts(self):
        for newline in (b'\n', b'\r\n'):
            for category in ('sourceInputs', 'evidenceFiles'):
                for path, record in self.a[category].items():
                    if record['bytePolicy'] == v.TEXT:
                        p = self.root / path
                        p.write_bytes(v.canonical_bytes(p.read_bytes(), v.TEXT).replace(b'\n', newline))
            self.assertEqual(v.verify(self.root, self.a)['status'], 'passed')

    def test_text_policy_preserves_bom_and_whitespace(self):
        original = b'\xef\xbb\xbfline \r\nnext\nlast\r'
        p = self.root / 'probe.txt'
        record = {'bytePolicy': v.TEXT, 'gitBlobSha256': v.sha(v.canonical_bytes(original, v.TEXT))}
        p.write_bytes(original)
        v.check_record(self.root, 'probe.txt', record)
        for changed in (original[3:], original.replace(b'line ', b'line'), original + b'\n', original.replace(b'next', b'edit')):
            p.write_bytes(changed)
            with self.assertRaises(ValueError):
                v.check_record(self.root, 'probe.txt', record)

    def test_binary_is_exact(self):
        p = self.root / 'binary'; p.write_bytes(b'\0\r\n')
        record = {'bytePolicy': v.EXACT, 'gitBlobSha256': v.sha(p.read_bytes())}
        p.write_bytes(b'\0\n')
        with self.assertRaises(ValueError): v.check_record(self.root, 'binary', record)
        with self.assertRaises(ValueError): v.canonical_bytes(b'\0\r\n', v.TEXT)

    def test_missing_source_is_rejected(self):
        self.a['sourceInputs'].pop(next(iter(self.a['sourceInputs'])))
        with self.assertRaisesRegex(ValueError, 'coverage'): v.verify(self.root, self.a)

    def test_changed_evidence_is_rejected(self):
        (self.root / self.a['gates']['desktop']).write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Content changed'): v.verify(self.root, self.a)

    def test_historical_link_is_checked(self):
        child = self.a['rawDigestLinks'][0]['child']
        self.a['evidenceFiles'][child]['originalSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Historical evidence'): v.verify(self.root, self.a)

    def test_commit_and_candidate_identity_are_checked(self):
        bad = copy.deepcopy(self.a); bad['sourceCommit'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'commit association'): v.verify(self.root, bad)
        bad = copy.deepcopy(self.a); bad['candidateIdentitySha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'candidate identity'): v.verify(self.root, bad)

    def test_wrong_archive_is_rejected(self):
        archive = self.root / 'wrong.zip'; archive.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'Archive changed'): v.verify(self.root, self.a, archive)

    def test_paths_cannot_escape_checkout(self):
        with self.assertRaises(ValueError): v.local(self.root, '../outside')


if __name__ == '__main__':
    unittest.main()
