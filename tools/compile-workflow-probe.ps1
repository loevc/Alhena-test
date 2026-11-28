$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$jdk = (Get-ChildItem (Join-Path $root '.cache\bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
$directory = Join-Path $root 'out\workflow'
New-Item -ItemType Directory -Path (Join-Path $directory 'classes') -Force | Out-Null
& (Join-Path $jdk javac.exe) -encoding UTF-8 --add-modules jdk.attach -d (Join-Path $directory 'classes') (Join-Path $PSScriptRoot 'smoke\Attach.java') (Join-Path $PSScriptRoot 'smoke\WorkflowLoader.java') (Join-Path $PSScriptRoot 'smoke\WorkflowProbe.java') (Join-Path $PSScriptRoot 'smoke\AdvancedProbe.java')
if ($LASTEXITCODE) { throw '工作流探针编译失败' }
$manifest = Join-Path $directory 'MANIFEST.MF'
Set-Content -LiteralPath $manifest -Value 'Agent-Class: WorkflowLoader' -Encoding ascii
$archive = Join-Path $directory ('workflow-' + [Guid]::NewGuid().ToString('N') + '.jar')
& (Join-Path $jdk jar.exe) cfm $archive $manifest -C (Join-Path $directory 'classes') .
if ($LASTEXITCODE) { throw '工作流探针打包失败' }
Set-Content -LiteralPath (Join-Path $directory 'agent-path.txt') -Value $archive -Encoding utf8
