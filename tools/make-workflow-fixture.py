"""Isolated repository, local bare remote and peer for original Git4Idea acceptance."""
from datetime import datetime
from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parents[1] / "out/fixtures" / datetime.now().strftime("workflow-%Y%m%d-%H%M%S")
root.mkdir(parents=True, exist_ok=False)
repo, remote, peer = (root / name for name in ("repo", "origin.git", "peer"))

def git(directory, *args):
    subprocess.run(["git", "-C", str(directory), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def identity(directory):
    for key, value in (("user.name", "Alhena Fixture"), ("user.email", "fixture@example.invalid"), ("commit.gpgsign", "false")):
        git(directory, "config", "--local", key, value)

repo.mkdir()
git(repo, "init", "-b", "main")
identity(repo)
(repo / ".git/info/exclude").write_text(".idea/\n", encoding="utf-8")
(repo / "README.md").write_text("# Workflow acceptance\n", encoding="utf-8")
(repo / "shared.txt").write_text("base version\n", encoding="utf-8")
git(repo, "add", ".")
git(repo, "commit", "-m", "Initialize workflow fixture")
git(repo, "checkout", "-b", "conflict-other")
(repo / "shared.txt").write_text("incoming version\n", encoding="utf-8")
git(repo, "commit", "-am", "Change incoming version")
git(repo, "checkout", "main")
(repo / "shared.txt").write_text("current version\n", encoding="utf-8")
git(repo, "commit", "-am", "Change current version")
git(repo, "branch", "feature/workflow")
git(root, "init", "--bare", "--initial-branch=main", str(remote))
git(repo, "remote", "add", "origin", str(remote))
git(repo, "push", "-u", "origin", "main")
git(root, "clone", str(remote), str(peer))
identity(peer)
(repo / "README.md").write_text("# Workflow acceptance\n\nCommit through the original staging UI.\n", encoding="utf-8")
(repo / "new-file.txt").write_text("Stage untracked files too.\n", encoding="utf-8")
print(json.dumps({"root": str(root), "repository": str(repo), "remote": str(remote), "peer": str(peer)}))
