"""Prepare a Windows CI package and publish its exact bytes from a pushed tag."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {'bin/alhena64.exe', 'lib/app.jar', 'plugins/vcs-git/lib/vcs-git.jar',
            'jbr/bin/java.exe', 'jbr/release', 'product-info.json', 'LICENSE.txt', 'NOTICE.txt'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def validate_tag(tag, version):
    pattern = r'v(\d+\.\d+\.\d+)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?'
    match = re.fullmatch(pattern, tag)
    if not match or match[1] != version.split('-')[0]:
        raise ValueError('Tag must be v<product version> with an optional prerelease suffix')


def inspect_package(archive, root):
    version = ET.parse(root / 'product/resources/idea/AlhenaApplicationInfo.xml').getroot().find('{*}version')
    lock = read(root / 'upstream.lock.json')
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or not REQUIRED <= set(names):
            raise ValueError('Incomplete or duplicate ZIP entries')
        if any(n.startswith(('/', '\\')) or '..' in n.replace('\\', '/').split('/') for n in names):
            raise ValueError('Unsafe ZIP path')
        if z.testzip() is not None:
            raise ValueError('ZIP CRC check failed')
        info = json.loads(z.read('product-info.json'))
        if info.get('name') != 'Alhena' or info.get('productCode') != 'AL' or info.get('version') != version.attrib['full']:
            raise ValueError('Package product identity differs from source')
        for name in ('bin/alhena64.exe', 'jbr/bin/java.exe'):
            if z.read(name)[:2] != b'MZ':
                raise ValueError('Invalid Windows executable: ' + name)
        plugins = {n.split('/')[1] for n in names if n.startswith('plugins/') and len(n.split('/')) > 2}
        if plugins != {'vcs-git'}:
            raise ValueError('Unexpected bundled plugins')
        for name in ('LICENSE.txt', 'NOTICE.txt'):
            upstream_notice = root / lock['checkout'] / name
            if z.read(name) != upstream_notice.read_bytes():
                raise ValueError('Upstream legal notice changed: ' + name)
    return info, version.attrib.get('eap') == 'true'


def prepare(archive, output, commit, tag='', root=ROOT, runtime_check=True):
    root = Path(root)
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected full source commit SHA')
    archive, output = Path(archive), Path(output)
    info, eap = inspect_package(archive, root)
    if tag:
        validate_tag(tag, info['version'])
    # Use the freshly built unpacked runtime, not any Java on PATH.
    if runtime_check:
        # The distribution directory is platform-build specific; extract only
        # the bundled runtime into a dedicated output directory instead.
        runtime_root = root / 'out/ci-runtime-smoke'
        if runtime_root.exists():
            raise ValueError('Runtime smoke directory already exists; use a fresh build output directory')
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                if item.filename.startswith('jbr/'):
                    z.extract(item, runtime_root)
        runtime = runtime_root / 'jbr/bin/java.exe'
        result = subprocess.run([str(runtime), '-version'], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('Bundled Java runtime failed to start')
    output.mkdir(parents=True, exist_ok=True)
    target = output / archive.name
    if archive.resolve() != target.resolve():
        shutil.copyfile(archive, target)
    checksum = output / (archive.name + '.sha256')
    checksum.write_text(digest(target) + '  ' + target.name + '\n', encoding='ascii')
    prerelease = eap or '-' in info['version'] or '-' in tag
    metadata = {'schemaVersion': 1, 'sourceCommit': commit, 'tag': tag,
                'productVersion': info['version'], 'buildNumber': info['buildNumber'],
                'upstreamCommit': read(root / 'upstream.lock.json')['commit'],
                'prerelease': prerelease, 'checks': {'zipCrc': 'passed', 'packageLayout': 'passed',
                'bundledRuntimeStartup': 'passed' if runtime_check else 'not_run'},
                'desktopAcceptance': 'not_run_on_hosted_runner',
                'runUrl': os.environ.get('ALHENA_RUN_URL', ''),
                'assets': [{'name': p.name, 'sha256': digest(p), 'bytes': p.stat().st_size} for p in (target, checksum)]}
    write(output / 'ci-package.json', metadata)
    notes = (f"Alhena {info['version']} for Windows x64.\n\n"
             "Extract the complete ZIP and run `bin/alhena64.exe`. Java is bundled; Git must be installed.\n\n"
             f"Source: `{commit}`\n\nTag: `{tag or 'manual candidate'}`\n\n"
             f"Upstream: `{metadata['upstreamCommit']}`\n\n"
             f"SHA-256 (`{target.name}`): `{digest(target)}`\n\n"
             "Automated checks: unit tests, Windows PowerShell 5.1 / PowerShell 7 syntax, ZIP integrity, "
             "product layout and bundled Java startup. Interactive desktop and real remote acceptance "
             "were not run on the hosted runner.\n\n"
             f"Build: {metadata['runUrl']}\n\n<!-- alhena-ci:{commit} -->\n")
    (output / 'release-notes.md').write_text(notes, encoding='utf-8')
    return metadata


class GitHub:
    def __init__(self):
        self.token = os.environ['GH_TOKEN']

    def request(self, path, method='GET', body=None, raw=None, missing_ok=False):
        url = 'https://api.github.com' + path if path.startswith('/') else path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'api.github.com', 'uploads.github.com'}:
            raise ValueError('Unexpected GitHub API host')
        headers = {'Authorization': 'Bearer ' + self.token, 'User-Agent': 'Alhena-CI',
                   'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        if raw is not None:
            data = Path(raw).read_bytes(); headers['Content-Type'] = 'application/octet-stream'
        else:
            data = json.dumps(body).encode() if body is not None else None
            if data is not None: headers['Content-Type'] = 'application/json'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if missing_ok and e.code == 404: return None
            raise RuntimeError(f'GitHub API {method} failed with HTTP {e.code}') from None


def local_assets(folder, metadata):
    expected = {a['name']: a for a in metadata['assets']}
    if len(expected) != 2 or not any(n.endswith('.win.zip') for n in expected) or not any(n.endswith('.win.zip.sha256') for n in expected):
        raise ValueError('Expected ZIP and SHA-256 assets')
    for name, item in expected.items():
        if Path(name).name != name or '\\' in name or '/' in name:
            raise ValueError('Unsafe asset name')
        p = folder / name
        if digest(p) != item['sha256'] or p.stat().st_size != item['bytes']:
            raise ValueError('Local release asset changed: ' + name)
    for name in ('ci-package.json', 'release-notes.md'):
        p = folder / name
        expected[name] = {'name': name, 'sha256': digest(p), 'bytes': p.stat().st_size}
    return expected


def verify_remote_assets(assets, expected, complete=True):
    actual = {a['name']: a for a in assets}
    if len(actual) != len(assets) or set(actual) - set(expected) or (complete and set(actual) != set(expected)):
        raise ValueError('Unexpected or missing release assets')
    for name, a in actual.items():
        e = expected[name]
        if a.get('state') != 'uploaded' or a.get('size') != e['bytes'] or a.get('digest') != 'sha256:' + e['sha256']:
            raise ValueError('Published asset differs: ' + name)
    return actual


def publish(folder, repository, tag, commit, client=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository')
    folder = Path(folder); metadata = read(folder / 'ci-package.json')
    validate_tag(tag, metadata['productVersion'])
    if metadata['tag'] != tag or metadata['sourceCommit'] != commit:
        raise ValueError('Artifact tag/source identity mismatch')
    expected = local_assets(folder, metadata)
    api = client or GitHub(); base = '/repos/' + repository
    encoded = urllib.parse.quote(tag, safe='')
    if api.request(base + '/commits/' + encoded)['sha'] != commit:
        raise ValueError('Remote tag does not resolve to this source commit')
    release = api.request(base + '/releases/tags/' + encoded, missing_ok=True)
    if release is None:
        # The tag endpoint promises published releases. Locate an authenticated
        # draft through the paginated listing when resuming a failed upload.
        matches, page = [], 1
        while True:
            rows = api.request(base + '/releases?per_page=100&page=' + str(page))
            matches.extend(row for row in rows if row['tag_name'] == tag)
            if len(rows) < 100:
                break
            page += 1
        if len(matches) > 1:
            raise ValueError('Multiple releases use this tag; inspect drafts before retrying')
        if matches:
            release = api.request(base + '/releases/' + str(matches[0]['id']))
    marker = '<!-- alhena-ci:' + commit + ' -->'
    if release is None:
        release = api.request(base + '/releases', 'POST', {'tag_name': tag, 'target_commitish': commit,
            'name': 'Alhena ' + tag, 'body': (folder / 'release-notes.md').read_text(encoding='utf-8'),
            'draft': True, 'prerelease': metadata['prerelease'], 'make_latest': 'false'})
    if marker not in (release.get('body') or '') or release['tag_name'] != tag or release['prerelease'] != metadata['prerelease']:
        raise ValueError('Existing release is not this CI candidate; refusing to replace it')
    present = verify_remote_assets(release['assets'], expected, complete=not release['draft'])
    if release['draft']:
        for name in expected.keys() - present.keys():
            upload = release['upload_url'].split('{')[0] + '?' + urllib.parse.urlencode({'name': name})
            api.request(upload, 'POST', raw=folder / name)
        release = api.request(base + '/releases/' + str(release['id']))
        verify_remote_assets(release['assets'], expected)
        if api.request(base + '/commits/' + encoded)['sha'] != commit:
            raise ValueError('Remote tag moved during upload')
        release = api.request(base + '/releases/' + str(release['id']), 'PATCH', {'draft': False})
    # Read back the published state and hashes; never delete or clobber assets.
    release = api.request(base + '/releases/' + str(release['id']))
    verify_remote_assets(release['assets'], expected)
    if release['draft']:
        raise ValueError('Release is still a draft')
    result = {'status': 'published_verified', 'url': release['html_url'], 'tag': tag,
              'sourceCommit': commit, 'prerelease': release['prerelease'], 'assets': list(expected.values())}
    write(folder / 'published-release.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'out/ci-release')
    p.add_argument('--commit', required=True); p.add_argument('--tag', default='')
    p = sub.add_parser('publish'); p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--repository', required=True); p.add_argument('--tag', required=True); p.add_argument('--commit', required=True)
    args = parser.parse_args()
    if args.action == 'prepare': result = prepare(args.archive, args.output, args.commit, args.tag)
    else: result = publish(args.folder, args.repository, args.tag, args.commit)
    print(json.dumps(result, indent=2))
