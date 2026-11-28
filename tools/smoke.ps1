param([string]$Archive)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$archiveArgument = @{}
if ($Archive) { $archiveArgument.Archive = $Archive }
$compiler = Get-ChildItem (Join-Path $root '.cache\bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1
if (!$compiler) { throw '请先构建产品，以准备上游 JBR SDK。' }
$jdk = $compiler.Directory.FullName
$evidence = Join-Path $root ('out\gui-smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$classes = Join-Path $evidence 'classes'
New-Item -ItemType Directory -Path $classes -Force | Out-Null
& (Join-Path $jdk javac.exe) --add-modules jdk.attach -d $classes (Join-Path $PSScriptRoot 'smoke\Attach.java') (Join-Path $PSScriptRoot 'smoke\UiProbe.java')
if ($LASTEXITCODE) { throw '界面探针编译失败' }
$manifest = Join-Path $evidence 'MANIFEST.MF'
Set-Content -LiteralPath $manifest -Value 'Agent-Class: UiProbe' -Encoding ascii
$agent = Join-Path $evidence 'ui-probe.jar'
& (Join-Path $jdk jar.exe) cfm $agent $manifest -C $classes .
if ($LASTEXITCODE) { throw '界面探针打包失败' }
$fixture = & python (Join-Path $PSScriptRoot 'make-fixture.py')
if ($LASTEXITCODE) { throw '创建专用测试仓库失败' }
$launch = (& (Join-Path $root 'run.ps1') @archiveArgument -Repository $fixture -Smoke -Hidden) | ConvertFrom-Json
$launch | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'launch.json') -Encoding utf8
$launch | ConvertTo-Json | Write-Output

function Invoke-Probe([string]$Stage) {
    # Never attach to a reused PID or any other application.
    $candidate = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $launch.pid)
    if (!$candidate -or $candidate.ExecutablePath -ne (Join-Path $launch.productRoot 'bin\alhena64.exe')) { throw '测试进程不存在或路径不匹配' }
    & (Join-Path $jdk java.exe) --add-modules jdk.attach -cp $classes Attach $launch.pid $agent ($evidence + '|' + $Stage)
    if ($LASTEXITCODE) { throw "界面探针失败：$Stage" }
    $result = Get-Content -LiteralPath (Join-Path $evidence ($Stage + '.txt')) -Raw
    if ($result -match '(?m)^.*(?:Exception|Error):') { throw "界面探针异常，见 $evidence" }
    return $result
}

function Wait-Probe([string]$Pattern, [string]$Stage = 'inspect') {
    $deadline = (Get-Date).AddSeconds(25)
    do {
        $snapshot = Invoke-Probe $Stage
        if ($snapshot -match $Pattern) { return $snapshot }
        Start-Sleep -Milliseconds 800
    } while ((Get-Date) -lt $deadline)
    throw "等待界面条件超时：$Pattern，见 $evidence"
}

try {
    [void](Wait-Probe 'openProjects=1')
    [void](Invoke-Probe 'activate')
    [void](Wait-Probe 'VcsLogMainGraphTable showing=true rows=5')
    [void](Wait-Probe '(?s)(?=.*BRANCH:main)(?=.*BRANCH:feature/history)(?=.*branchesVisibleWidth=[1-9][0-9]{2,})' 'expand')
    Copy-Item -LiteralPath (Join-Path $evidence 'expand-0.png') -Destination (Join-Path $evidence 'git-log.png')
    [void](Invoke-Probe 'select')
    [void](Wait-Probe '(?m)^node=.*history\.txt')
    $diff = Invoke-Probe 'diff'
    if ($diff -notmatch 'canShowDiff=true') { throw '提交变更未能提供 Diff' }
    [void](Wait-Probe 'diffComponent=.*Twoside')
    Copy-Item -LiteralPath (Join-Path $evidence 'inspect-0.png') -Destination (Join-Path $evidence 'commit-diff.png')
    $log = Get-Content -LiteralPath (Join-Path $launch.sandbox 'log\idea.log') -Raw
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw "启动或交互出现严重错误，见 $($launch.sandbox)\log\idea.log" }
    $summary = [ordered]@{ status = 'passed'; archiveSha256 = $launch.archiveSha256; evidence = $evidence; fixture = $fixture; checks = @('native ZIP launch','isolated config','Git4Idea enabled','5 commits with merge graph','main and feature/history branch tree','commit selection loads history.txt','original two-sided Diff','no SEVERE/ERROR log entries') }
    $summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'result.json') -Encoding utf8
    $summary | ConvertTo-Json
} finally {
    $candidate = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $launch.pid)
    if ($candidate -and $candidate.ExecutablePath -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) { Stop-Process -Id $launch.pid }
}
