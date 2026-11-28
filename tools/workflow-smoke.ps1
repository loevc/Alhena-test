param([string]$Archive)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$archiveArgument = @{}
if ($Archive) { $archiveArgument.Archive = $Archive }
& (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
$fixture = (& python (Join-Path $PSScriptRoot 'make-workflow-fixture.py')) | ConvertFrom-Json
if ($LASTEXITCODE) { throw '创建工作流测试仓库失败' }
$relative = 'out\workflow-smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$evidence = Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$fixture | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'fixture.json') -Encoding utf8
$launch = (& (Join-Path $root 'run.ps1') @archiveArgument -Repository $fixture.repository -Smoke -Hidden) | ConvertFrom-Json
$launch | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'launch.json') -Encoding utf8
$checks = [Collections.Generic.List[string]]::new()

function Read-Git([string[]]$GitArgs, [string]$Directory = $fixture.repository) {
    $value = & git -C $Directory @GitArgs
    if ($LASTEXITCODE) { throw "Git 验证命令失败：$GitArgs" }
    return ($value -join "`n").Trim()
}
function Wait-Until([scriptblock]$Condition, [string]$Name) {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        if (& $Condition) { $checks.Add($Name); Write-Output "PASS $Name"; return }
        Start-Sleep -Milliseconds 400
    } while ((Get-Date) -lt $deadline)
    throw "等待条件超时：$Name"
}
function Probe([string]$Stage, [string]$Payload = '', [string]$Step = $Stage) {
    return (& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage $Stage -Payload $Payload -Evidence ($relative + '\' + $Step)) -join "`n"
}
function Wait-Ui([string]$Pattern, [string]$Step) {
    Wait-Until { (Probe 'ui-inspect' '' $Step) -match $Pattern } $Step
}
try {
    Wait-Until {
        $path = Join-Path $launch.sandbox 'log\idea.log'
        (Test-Path -LiteralPath $path) -and ((Get-Content -LiteralPath $path -Raw) -match 'Git version for ')
    } 'native startup and Git detection'
    [void](Probe 'ui-stage-open')
    Wait-Ui '(?s)GitStagePanel.*Unstaged.*new-file.txt.*README.md' 'unstaged-files'
    [void](Probe 'ui-stage-all')
    Wait-Until { (Read-Git @('diff','--cached','--name-only')) -eq "README.md`nnew-file.txt" } 'original Stage All writes index'
    Wait-Ui '(?m)^node=\[, Staged, .*README.md\]' 'staged-files'
    [void](Probe 'ui-message' 'Commit through original staging UI' 'commit')
    [void](Probe 'ui-commit' '' 'commit')
    Wait-Until { (Read-Git @('log','-1','--format=%s')) -eq 'Commit through original staging UI' } 'original Commit button creates commit'
    if (Read-Git @('status','--porcelain')) { throw '提交后工作区不干净' }
    $committedHead=Read-Git @('rev-parse','HEAD')
    [void](Probe 'ui-message' 'Reject arbitrary empty commit' 'empty-commit-rejected')
    [void](Probe 'ui-commit' '' 'empty-commit-rejected')
    Wait-Ui 'label=.*Stage files to commit' 'empty-commit-rejected'
    if((Read-Git @('rev-parse','HEAD')) -ne $committedHead) { throw '普通空提交不应被创建' }
    [void](Probe 'ui-checkout' 'feature/workflow' 'checkout-feature')
    Wait-Until { (Read-Git @('branch','--show-current')) -eq 'feature/workflow' } 'original branch checkout'
    [void](Probe 'ui-checkout' 'main' 'checkout-main')
    Wait-Until { (Read-Git @('branch','--show-current')) -eq 'main' } 'original branch checkout back'
    [void](Probe 'ui-push-open' '' 'push')
    Wait-Ui '(?s)PushLog.*Commit through original staging UI.*button=Push enabled=true' 'push'
    [void](Probe 'ui-push' '' 'push')
    Wait-Until { (Read-Git @('rev-parse','main') $fixture.remote) -eq (Read-Git @('rev-parse','HEAD')) } 'original Push updates local bare remote'
    & git -C $fixture.peer pull --ff-only | Out-Null
    if ($LASTEXITCODE) { throw '测试 peer 拉取失败' }
    [IO.File]::WriteAllText((Join-Path $fixture.peer 'remote-update.txt'), "Incoming from the local test peer.`n")
    & git -C $fixture.peer add remote-update.txt
    & git -C $fixture.peer commit -m 'Publish incoming peer update' | Out-Null
    if ($LASTEXITCODE) { throw '测试 peer 提交失败' }
    & git -C $fixture.peer push origin main
    if ($LASTEXITCODE) { throw '测试 peer 推送失败' }
    $peerHead = Read-Git @('rev-parse','HEAD') $fixture.peer
    [void](Probe 'ui-fetch')
    Wait-Until { (Read-Git @('rev-parse','origin/main')) -eq $peerHead } 'original Fetch updates remote tracking ref'
    [void](Probe 'ui-update-open' '' 'update')
    Wait-Ui 'title=Update Project' 'update'
    [void](Probe 'ui-update' '' 'update')
    Wait-Until { (Read-Git @('rev-parse','HEAD')) -eq $peerHead } 'original Update Project integrates peer commit'
    if (!(Test-Path -LiteralPath (Join-Path $fixture.repository 'remote-update.txt'))) { throw '更新文件不存在' }
    $merge = Probe 'api-merge-conflict' '' 'conflict'
    if ($merge -notmatch 'expectedConflictExit=1' -or !(Read-Git @('ls-files','-u'))) { throw '测试冲突未生成' }
    $data = Probe 'api-conflict-data' '' 'conflict'
    foreach ($side in @('CURRENT=current version','ORIGINAL=base version','LAST=incoming version')) {
        if (!$data.Contains('mergeData.'+$side)) { throw "原版 MergeProvider 内容错误：$side" }
    }
    [void](Probe 'ui-conflict-open' '' 'conflict-dialog')
    Wait-Ui 'MergeConflictsTreeTable' 'conflict-dialog'
    [void](Probe 'ui-click' 'Merge...' 'three-way-merge')
    Wait-Ui '(?s)ThreeDiffSplitter.*button=Accept Left enabled=true' 'three-way-merge'
    [void](Probe 'ui-click' 'Accept Left' 'resolve')
    Wait-Until { !(Read-Git @('ls-files','-u')) -and (Get-Content -LiteralPath (Join-Path $fixture.repository 'shared.txt') -Raw).Trim() -eq 'current version' } 'original merge UI resolves index with selected content'
    Wait-Ui 'GitStagePanel.*rows=0' 'merge-ready'
    [void](Probe 'ui-message' 'Resolve fixture merge through original UI' 'merge-commit')
    [void](Probe 'ui-commit' '' 'merge-commit')
    Wait-Until { (Read-Git @('log','-1','--format=%s')) -eq 'Resolve fixture merge through original UI' } 'original staging workflow finishes no-diff merge'
    $parents = (Read-Git @('log','-1','--format=%P')).Split(' ')
    if ($parents.Count -ne 2 -or (Test-Path -LiteralPath (Join-Path $fixture.repository '.git\MERGE_HEAD')) -or (Read-Git @('status','--porcelain'))) { throw '合并提交的父节点、状态或工作区验证失败' }
    $log = Get-Content -LiteralPath (Join-Path $launch.sandbox 'log\idea.log') -Raw
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw "测试日志出现严重错误：$($launch.sandbox)\log\idea.log" }
    $checks.Add('two-parent merge commit, clean index and working tree, no severe log errors')
    $result = [ordered]@{ status='passed'; archiveSha256=$launch.archiveSha256; evidence=$evidence; fixture=$fixture; head=(Read-Git @('rev-parse','HEAD')); parents=$parents; checks=$checks.ToArray() }
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 5
} finally {
    $candidate = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $launch.pid)
    if ($candidate -and $candidate.ExecutablePath -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) { Stop-Process -Id $launch.pid }
}
