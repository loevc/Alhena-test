"""Dedicated history and two-hunk fixture for original Git4Idea acceptance."""
from datetime import datetime
import json
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parents[1] / "out/fixtures" / datetime.now().strftime("workflow-advanced-%Y%m%d-%H%M%S")
repo.mkdir(parents=True, exist_ok=False)


def git(*args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE, text=True).strip()


def commit(message, author="Alhena Fixture"):
    git("add", ".")
    git("-c", "user.name=" + author, "-c", "user.email=fixture@example.invalid", "commit", "-m", message)
    return git("rev-parse", "HEAD")


git("init", "-b", "main")
git("config", "user.name", "Alhena Fixture")
git("config", "user.email", "fixture@example.invalid")
git("config", "commit.gpgsign", "false")
(repo / ".git/info/exclude").write_text(".idea/\n*.iml\n", encoding="utf-8")
(repo / "hunks.txt").write_text("".join(f"line {i:02d}\n" for i in range(40)), encoding="utf-8")
(repo / "history.txt").write_text("First line\nSecond line\nThird line\n", encoding="utf-8")
base = commit("Initialize advanced fixture", "Alhena Base")
(repo / "history.txt").write_text("First line\nUpdated second line\nThird line\n", encoding="utf-8")
history = commit("Update file history line", "Alhena Author")
git("checkout", "-b", "cherry-source")
(repo / "cherry.txt").write_text("Cherry-picked content\n", encoding="utf-8")
cherry = commit("Accept cherry-pick source")
git("checkout", "main")
git("checkout", "-b", "upstream-target")
(repo / "upstream.txt").write_text("Upstream rebase content\n", encoding="utf-8")
upstream = commit("Upstream rebase target")
git("checkout", "-b", "rebase-feature", history)
(repo / "rebase.txt").write_text("Feature rebase content\n", encoding="utf-8")
feature = commit("Replay this feature commit")
git("checkout", "main")
lines = (repo / "hunks.txt").read_text().splitlines()
lines[2] = "first hunk change"
lines[34] = "second hunk change"
(repo / "hunks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"repository": str(repo), "base": base, "history": history, "cherry": cherry,
                  "upstream": upstream, "feature": feature}))
