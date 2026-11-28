"""Create a dedicated Git repository for GUI acceptance, never the user repository."""
from datetime import datetime
import argparse
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--suffix", default="")
parser.add_argument("--existing-project", action="store_true")
args = parser.parse_args()
if any(char in args.suffix for char in '/\\:<>"|?*') or args.suffix.endswith((".", " ")):
    raise SystemExit("Invalid fixture suffix")
root = Path(__file__).resolve().parents[1] / "out/fixtures" / (datetime.now().strftime("history-%Y%m%d-%H%M%S") + args.suffix)
root.mkdir(parents=True, exist_ok=False)


def git(*args):
    subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def commit(message):
    git("add", "--all")
    git("-c", "user.name=Alhena Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", message)


git("init", "-b", "main")
(root / "README.md").write_text("# Alhena GUI fixture\n\nRead history and compare revisions.\n", encoding="utf-8")
commit("Initialize history fixture")
git("checkout", "-b", "feature/history")
(root / "history.txt").write_text("Commit graph\nBranch filtering\n", encoding="utf-8")
commit("Add history browser notes")
(root / "history.txt").write_text("Commit graph\nBranch filtering\nSide-by-side diff\n", encoding="utf-8")
commit("Describe side-by-side diff")
git("checkout", "main")
(root / "notes.txt").write_text("Verify original Git4Idea UI.\n", encoding="utf-8")
commit("Document platform verification")
git("-c", "user.name=Alhena Fixture", "-c", "user.email=fixture@example.invalid", "merge", "--no-ff", "feature/history", "-m", "Merge history workflow")
if args.existing_project:
    (root / ".idea").mkdir()
    (root / ".idea/modules.xml").write_text('''<project version="4"><component name="ProjectModuleManager"><modules>
<module fileurl="file://$PROJECT_DIR$/repo.iml" filepath="$PROJECT_DIR$/repo.iml"/>
</modules></component></project>''', encoding="utf-8")
    (root / ".idea/vcs.xml").write_text('''<project version="4"><component name="VcsDirectoryMappings">
<mapping directory="$PROJECT_DIR$" vcs="Git"/></component></project>''', encoding="utf-8")
    (root / "repo.iml").write_text('''<module type="JAVA_MODULE" version="4"><component name="NewModuleRootManager">
<content url="file://$MODULE_DIR$"/><orderEntry type="inheritedJdk"/><orderEntry type="sourceFolder" forTests="false"/>
</component></module>''', encoding="utf-8")
print(root)
