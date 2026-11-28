"""Check the actual script files with Windows PowerShell 5.1 and PowerShell 7."""
import base64
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [ROOT / "build.ps1", ROOT / "run.ps1", *sorted((ROOT / "tools").rglob("*.ps1"))]


class PowerShellScriptTests(unittest.TestCase):
    def test_non_ascii_scripts_have_utf8_bom(self):
        for path in SCRIPTS:
            with self.subTest(script=path.relative_to(ROOT)):
                data = path.read_bytes()
                if not data.decode("utf-8-sig").isascii():
                    self.assertTrue(data.startswith(b"\xef\xbb\xbf"), "Windows PowerShell 5.1 needs a BOM for UTF-8 scripts")

    @unittest.skipUnless(os.name == "nt", "Windows parser compatibility")
    def test_parse_with_installed_windows_powershell_and_pwsh(self):
        paths = ",".join("'" + str(path).replace("'", "''") + "'" for path in SCRIPTS)
        code = "$failed=$false; foreach($path in @(" + paths + ")) { $errors=$null; $tokens=$null; " + \
               "[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors) | Out-Null; " + \
               "if($errors.Count) { $failed=$true; Write-Output $path; $errors | ForEach-Object { Write-Output $_.Message } } }; " + \
               "if($failed) { exit 1 }"
        encoded = base64.b64encode(code.encode("utf-16-le")).decode("ascii")
        shells = [Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"]
        pwsh = shutil.which("pwsh.exe")
        if pwsh:
            shells.append(Path(pwsh))
        for shell in shells:
            with self.subTest(shell=str(shell)):
                result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))
