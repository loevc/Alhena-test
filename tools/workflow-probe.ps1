param([Parameter(Mandatory=$true)][string]$Stage, [string]$Payload = '', [string]$Evidence = 'out\workflow')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$launch = Get-Content -LiteralPath (Join-Path $root 'out\last-launch.json') -Raw | ConvertFrom-Json
$candidate = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $launch.pid)
if (!$candidate -or $candidate.ExecutablePath -ne (Join-Path $launch.productRoot 'bin\alhena64.exe')) { throw '测试进程不存在或路径不匹配' }
$fixtureRoot = [IO.Path]::GetFullPath((Join-Path $root 'out\fixtures')) + [IO.Path]::DirectorySeparatorChar
if (!$launch.repository.StartsWith($fixtureRoot, [StringComparison]::OrdinalIgnoreCase)) { throw '拒绝对非测试仓库执行操作' }
$jdk = (Get-ChildItem (Join-Path $root '.cache\bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
$directory = [IO.Path]::GetFullPath((Join-Path $root $Evidence))
if (!$directory.StartsWith($root + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '证据目录超出工作区' }
$agent = (Get-Content -LiteralPath (Join-Path $root 'out\workflow\agent-path.txt') -Raw).Trim()
& (Join-Path $jdk java.exe) --add-modules jdk.attach -cp (Join-Path $root 'out\workflow\classes') Attach $launch.pid $agent ($directory + '|' + $Stage + '|' + $Payload + '|' + $agent)
if ($LASTEXITCODE) { throw "探针失败：$Stage" }
$report = Get-Content -LiteralPath (Join-Path $directory ($Stage + '.txt')) -Raw
if ($report -match '(?m)^.*(?:Exception|Error):') { throw "探针异常，见 $directory\$Stage.txt" }
if (Test-Path -LiteralPath (Join-Path $directory 'async-errors.txt')) { throw "异步界面探针异常，见 $directory\async-errors.txt" }
$report
