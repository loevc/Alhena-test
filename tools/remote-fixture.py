"""Prepare/revoke a repo-scoped GitHub acceptance fixture; never persists tokens.

Only a separately authorized test repository may be used. Private test keys live
under ignored .cache, and deploy keys are removed by the cleanup command.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/remote-test"
HOST_FINGERPRINT = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"


def run(args, cwd=None, env=None, input=None, timeout=90):
    result = subprocess.run(args, cwd=cwd, env=env, input=input, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        # Do not expose command arguments: credential/key commands can contain secrets.
        raise RuntimeError(f"{Path(args[0]).name} failed with exit code {result.returncode}")
    return result.stdout.strip()


def git(repo, *args, env=None):
    return run(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args], env=env)


def environment():
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    return env


def token(repository):
    text = run(["git", "credential", "fill"], input=f"protocol=https\nhost=github.com\npath={repository}.git\n\n", env=environment())
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if not values.get("password"):
        raise RuntimeError("No non-interactive GitHub credential in configured Git helper")
    return values["password"]


def api(path, secret=None, method="GET", body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Alhena-Acceptance"}
    if secret:
        headers["Authorization"] = "Bearer " + secret
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request("https://api.github.com" + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    return json.loads(payload) if payload else None


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def validate_target(repository):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Use owner/repository")
    origin = git(ROOT, "remote", "get-url", "origin")
    source = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", origin)
    if source and source.group(1).lower() == repository.lower():
        raise ValueError("Refuse to test-write to the Alhena source repository")


def prepare(repository):
    validate_target(repository)
    secret = token(repository)
    info = api("/repos/" + repository, secret)
    if not info.get("permissions", {}).get("admin"):
        raise RuntimeError("Test repository admin access is needed for its temporary deploy key")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = CACHE / run_id
    folder.mkdir(parents=True, exist_ok=False)
    context_path = folder / "context.json"
    host_key = next(key for key in api("/meta")["ssh_keys"] if key.startswith("ssh-ed25519 "))
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(host_key.split()[1])).digest()).decode().rstrip("=")
    if fingerprint != HOST_FINGERPRINT:
        raise RuntimeError("GitHub host key differs from the officially documented fingerprint")
    hosts = folder / "known_hosts"
    hosts.write_text("github.com " + host_key + "\n", encoding="ascii")
    private = folder / "id_ed25519"
    run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "Alhena acceptance " + run_id, "-f", str(private)])
    public = private.with_suffix(".pub").read_text(encoding="ascii").strip()
    try:
        key = api("/repos/" + repository + "/keys", secret, "POST",
                  {"title": "Alhena acceptance " + run_id, "key": public, "read_only": False})
    except BaseException:
        private.unlink(missing_ok=True)
        raise
    context = {"schemaVersion": 1, "repository": repository, "runId": run_id, "deployKeyId": key["id"],
               "privateKeyPath": str(private), "knownHostsPath": str(hosts), "hostKeyFingerprint": fingerprint,
               "httpsUrl": f"https://github.com/{repository}.git", "sshUrl": f"git@github.com:{repository}.git",
               "seedBranch": "alhena-acceptance-" + run_id, "status": "prepared-key"}
    save(context_path, context)
    try:
        ssh = ["ssh", "-T", "-i", str(private), "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "UserKnownHostsFile=" + str(hosts), "-o", "BatchMode=yes", "git@github.com"]
        result = subprocess.run(ssh, env=environment(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        if "successfully authenticated" not in result.stdout:
            raise RuntimeError("Repo-scoped SSH key did not authenticate")
        seed = Path(run([sys.executable, str(ROOT / "tools/make-fixture.py"), "--suffix=-remote-seed"]))
        git(seed, "remote", "add", "origin", context["httpsUrl"])
        git(seed, "push", "origin", "HEAD:refs/heads/" + context["seedBranch"], env=environment())
        context.update(seedRepository=str(seed), seedHead=git(seed, "rev-parse", "HEAD"), status="ready")
        save(context_path, context)
        save(CACHE / "latest.json", {"context": str(context_path)})
    except BaseException:
        try:
            cleanup(context_path)
        except Exception:
            # cleanup records pending revocation and always removes the local key.
            pass
        raise
    print(json.dumps({"status": "ready", "context": str(context_path), "repository": repository,
                      "httpsCanPush": True, "sshAuthenticated": True, "seedBranch": context["seedBranch"]}))


def cleanup(context_path):
    context_path = context_path.resolve()
    if not context_path.is_relative_to(CACHE.resolve()):
        raise ValueError("Context must be under project .cache/remote-test")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    validate_target(context["repository"])
    private = Path(context["privateKeyPath"]).resolve()
    if private.parent != context_path.parent or private.name != "id_ed25519":
        raise ValueError("Private key path escaped cache")
    try:
        if context.get("deployKeyId") is not None:
            path = "/repos/" + context["repository"] + "/keys/" + str(context["deployKeyId"])
            secret = token(context["repository"])
            key = api(path, secret)
            public = private.with_suffix(".pub").read_text(encoding="ascii").strip()
            if key["title"] != "Alhena acceptance " + context["runId"] or key["key"].split()[:2] != public.split()[:2]:
                raise ValueError("Refuse to revoke a deploy key not owned by this run")
            api(path, secret, "DELETE")
            context["deployKeyId"] = None
    finally:
        private.unlink(missing_ok=True)
        context["status"] = "cleaned" if context.get("deployKeyId") is None else "key-revocation-pending"
        save(context_path, context)
    print(json.dumps({"status": "cleaned", "repository": context["repository"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("prepare")
    create.add_argument("--repository", required=True)
    revoke = sub.add_parser("cleanup")
    revoke.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.repository)
    else:
        cleanup(args.context)
