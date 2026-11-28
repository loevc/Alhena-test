"""Verify a tested candidate against its canonical Git source and portable evidence.

Historical raw SHA-256 values are retained. The association additionally binds
Git-stored bytes to the tested CI blobs; UTF-8 text permits CRLF -> LF only.
No whitespace trimming, BOM removal or binary normalization is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = 'utf8-crlf-to-lf-preserve-bom-v1'
EXACT = 'exact-bytes-v1'
IDENTITY_FIELDS = ('archiveSha256', 'archiveBytes', 'sourceInputSha256',
                   'sourceProductSha256', 'patchManifestSha256',
                   'packagedClassesMatchBuildOutput', 'versionMetadata',
                   'productInfoVersion', 'productInfoBuildNumber')
DESKTOP_CASES = {'native-switch', 'cli-ps51', 'cli-ps7', 'product', 'graph-diff', 'workflow', 'workspace', 'advanced'}
REMOTE_CASES = {'https-clone', 'https-sync', 'ssh-clone', 'ssh-sync', 'https-auth-cancel', 'ssh-auth-rejected', 'network-failure'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(data, policy):
    if policy == EXACT:
        return data
    if policy != TEXT:
        raise ValueError('Unknown byte policy')
    data.decode('utf-8')  # Deliberately preserves a UTF-8 BOM.
    if b'\0' in data:
        raise ValueError('Binary data cannot use text normalization')
    return data.replace(b'\r\n', b'\n')


def identity(candidate):
    value = {key: candidate[key] for key in IDENTITY_FIELDS if key in candidate}
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def local(root, relative):
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('Path outside checkout: ' + relative)
    return path


def check_record(root, relative, record):
    data = local(root, relative).read_bytes()
    if sha(canonical_bytes(data, record['bytePolicy'])) != record['gitBlobSha256']:
        raise ValueError('Content changed: ' + relative)


def verify(root, association, archive=None):
    root = Path(root).resolve()
    if association.get('schemaVersion') != 1:
        raise ValueError('Unsupported association schema')
    candidate = read(local(root, association['candidate']))
    if candidate.get('sourceCommit') != association['sourceCommit'] or not candidate.get('sourceChangesCommitted'):
        raise ValueError('Canonical source commit association mismatch')
    if identity(candidate) != association['candidateIdentitySha256']:
        raise ValueError('Tested candidate identity changed')
    if candidate['archiveSha256'] != association['archiveSha256']:
        raise ValueError('Mixed candidate archives')
    sources = association['sourceInputs']
    if set(sources) != set(candidate['sourceInputSha256']):
        raise ValueError('Incomplete source coverage')
    for path, record in sources.items():
        if record['originalSha256'] != candidate['sourceInputSha256'][path]:
            raise ValueError('Historical source digest changed: ' + path)
        if record['gitBlobSha256'] != record['testedCiBlobSha256']:
            raise ValueError('Source differs from tested CI blob: ' + path)
        check_record(root, path, record)
    evidence = association['evidenceFiles']
    for path, record in evidence.items():
        check_record(root, path, record)
    ci = read(local(root, association['ciEvidence']))
    if association['ciEvidence'] not in evidence or ci['ciCanonicalSourceCommit'] != association['testedCiSourceCommit']:
        raise ValueError('Unanchored CI source identity')
    for path, record in sources.items():
        if ci['committedBlobSha256'].get(path) != record['gitBlobSha256']:
            raise ValueError('CI evidence source mismatch: ' + path)
    for link in association['rawDigestLinks']:
        if link['parent'] not in evidence or link['child'] not in evidence:
            raise ValueError('Unanchored evidence link')
        value = read(local(root, link['parent']))
        for key in link['keys']:
            value = value[key]
        if value != evidence[link['child']]['originalSha256']:
            raise ValueError('Historical evidence digest changed: ' + link['child'])
    for kind, required in (('desktop', DESKTOP_CASES), ('remote', REMOTE_CASES)):
        relative = association['gates'][kind]
        if relative not in evidence:
            raise ValueError('Unanchored gate report')
        report = read(local(root, relative))
        if report.get('status') != 'passed' or set(report['cases']) != required:
            raise ValueError('Incomplete ' + kind + ' gate')
        if report['archiveSha256'] != candidate['archiveSha256'] or report['sourceSha256'] != candidate['sourceInputSha256']:
            raise ValueError('Gate archive/source identity mismatch')
        if kind == 'remote' and not report.get('temporaryKeyRevoked'):
            raise ValueError('Remote key revocation not confirmed')
        for name, item in report['cases'].items():
            child = (Path(relative).parent / (name + '.json')).as_posix()
            if child not in evidence:
                raise ValueError('Missing case evidence: ' + name)
            result = read(local(root, child))
            if result.get('status') != 'passed' or result.get('archiveSha256') != candidate['archiveSha256'] or not result.get('checks'):
                raise ValueError('Failed case or mixed archives: ' + name)
            if result.get('evidence') != item['originalEvidence']:
                raise ValueError('Case identity mismatch: ' + name)
            if kind == 'desktop':
                if name == 'native-switch' and not all(result.get(k) for k in ('repositorySwitching', 'nativeSelection', 'existingProject')):
                    raise ValueError('Missing native switching coverage')
                if name.startswith('cli-'):
                    version = '5.1.' if name == 'cli-ps51' else '7.'
                    if not result.get('commandLineMode') or not result.get('existingProject') or not result.get('powerShellVersion', '').startswith(version):
                        raise ValueError('Wrong command-line coverage')
    archive_verified = False
    if archive is not None:
        if sha(Path(archive).read_bytes()) != candidate['archiveSha256']:
            raise ValueError('Archive changed')
        archive_verified = True
    return {'status': 'passed', 'sourceCommit': association['sourceCommit'],
            'sourceFilesVerified': len(sources), 'evidenceFilesVerified': len(evidence),
            'archiveVerified': archive_verified, 'releaseReady': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--association', type=Path, default=ROOT / 'docs/evidence/source-association.json')
    parser.add_argument('--archive', type=Path, help='Optional exact tested ZIP; not needed to verify a source-only checkout')
    args = parser.parse_args()
    print(json.dumps(verify(ROOT, read(args.association), args.archive), indent=2))
