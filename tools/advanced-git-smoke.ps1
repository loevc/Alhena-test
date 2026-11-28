param([string]$Archive)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$archiveArgument = @{}
if ($Archive) { $archiveArgument.Archive = $Archive }
& (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
$fixture = (& python (Join-Path $PSScriptRoot 'make-advanced-fixture.py')) | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Advanced fixture failed' }
$relative = 'out\advanced-git-smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$evidence = Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$fixture | ConvertTo-Json | Set-Content (Join-Path $evidence 'fixture.json') -Encoding utf8
$launch = (& (Join-Path $root 'run.ps1') @archiveArgument -Repository $fixture.repository -Smoke -Hidden) | ConvertFrom-Json
$launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'launch.json') -Encoding utf8
$checks = [Collections.Generic.List[string]]::new()
function Read-Git([string[]]$Arguments) {
    $value = & git.exe -C $fixture.repository @Arguments
    if ($LASTEXITCODE) { throw "Git verification failed: $($Arguments[0])" }
    return ($value -join "`n").Trim()
}
function Probe([string]$Stage,[string]$Payload='', [string]$Step=$Stage) {
    (& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage $Stage -Payload $Payload -Evidence ($relative+'\'+$Step)) -join "`n"
}
function Wait-Until([scriptblock]$Condition,[string]$Name) {
    $deadline=(Get-Date).AddSeconds(40)
    do {
        if (& $Condition) { $checks.Add($Name); Write-Output "PASS $Name"; return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Timed out: $Name; see $evidence"
}
try {
    Wait-Until {
        $log=Join-Path $launch.sandbox 'log\idea.log'
        (Test-Path $log) -and ((Get-Content $log -Raw) -match 'Git version for ')
    } 'native Git ready'
    Wait-Until { (Probe ui-inspect '' 'startup-history') -match 'selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor' } 'initial central workspace ready before opening fixture file'
    [void](Probe ui-advanced-open-hunks)
    Wait-Until { ([regex]::Matches((Probe ui-advanced-state '' 'hunks-ready'),'(?m)^hunk=')).Count -eq 2 } 'original staging line tracker sees two separated hunks'
    [void](Probe ui-advanced-hunk-popup '' 'hunk-popup')
    Wait-Until { (Probe ui-advanced-state '' 'hunk-popup') -match 'originalHunkLink=Stage' } 'original hunk popup exposes Stage link'
    [void](Probe ui-advanced-hunk-stage '' 'stage-first-hunk')
    Wait-Until { (Read-Git @('show',':hunks.txt')) -match 'first hunk change' } 'original hunk Stage writes index'
    if ((Read-Git @('show',':hunks.txt')) -match 'second hunk change') { throw 'Staging one hunk staged the other hunk' }
    if ((Read-Git @('diff','--','hunks.txt')) -notmatch 'second hunk change') { throw 'Unselected hunk lost from worktree diff' }
    $checks.Add('selected hunk alone is staged, second hunk remains unstaged')
    Wait-Until { (Probe ui-advanced-state '' 'hunk-unstage') -match 'originalHunkLink=Unstage' } 'original popup exposes Unstage link'
    [void](Probe ui-advanced-hunk-unstage '' 'hunk-unstage')
    Wait-Until { !(Read-Git @('diff','--cached','--name-only')) } 'original hunk Unstage clears index'
    $working = Get-Content (Join-Path $fixture.repository 'hunks.txt') -Raw
    if ($working -notmatch 'first hunk change' -or $working -notmatch 'second hunk change') { throw 'Hunk Unstage changed working content' }
    [void](Probe ui-advanced-popup-close)
    [void](Probe ui-stage-open)
    Wait-Until { (Probe ui-inspect '' 'prepare-commit') -match 'GitStagePanel' } 'staging panel ready'
    [void](Probe ui-stage-all)
    Wait-Until { (Probe ui-inspect '' 'prepare-commit') -match '(?m)^node=\[, Staged, .*hunks.txt\]' } 'both fixture hunks staged for clean branch tests'
    [void](Probe ui-message 'Accept both fixture hunks' 'prepare-commit')
    [void](Probe ui-commit '' 'prepare-commit')
    Wait-Until { (Read-Git @('log','-1','--format=%s')) -eq 'Accept both fixture hunks' } 'original Commit prepares clean advanced fixture'
    if (Read-Git @('status','--porcelain')) { throw 'Branch fixture must be clean' }
    $startHead = Read-Git @('rev-parse','HEAD')
    [void](Probe ui-advanced-branch-create '' 'branch-create')
    Wait-Until { (Probe ui-inspect '' 'branch-create') -match 'button=Create enabled=true|title=.*[Bb]ranch' } 'original New Branch dialog'
    [void](Probe ui-advanced-branch-name 'acceptance/created' 'branch-create')
    [void](Probe ui-advanced-branch-submit 'Create' 'branch-create')
    Wait-Until { (Probe ui-advanced-state '' 'created') -match 'currentBranch=acceptance/created' } 'original Create dialog creates and checks out branch'
    if ((Read-Git @('rev-parse','HEAD')) -ne $startHead) { throw 'New branch started at wrong commit' }
    [void](Probe ui-advanced-branch-rename '' 'branch-rename')
    Wait-Until { (Probe ui-inspect '' 'branch-rename') -match 'button=Rename enabled=true|title=.*[Rr]ename' } 'original Rename Branch dialog'
    [void](Probe ui-advanced-branch-name 'acceptance/renamed' 'branch-rename')
    [void](Probe ui-advanced-branch-submit 'Rename' 'branch-rename')
    Wait-Until { (Probe ui-advanced-state '' 'renamed') -match 'currentBranch=acceptance/renamed' } 'original Rename changes current branch'
    if ((Read-Git @('branch','--list','acceptance/created')) -or (Read-Git @('rev-parse','acceptance/renamed')) -ne $startHead) { throw 'Rename refs differ' }
    [void](Probe ui-checkout 'main' 'branch-checkout-main')
    Wait-Until { (Probe ui-advanced-state '' 'checkout-main') -match 'currentBranch=main' } 'original checkout returns to main'
    [void](Probe ui-advanced-branch-delete '' 'branch-delete')
    Wait-Until { !(Read-Git @('branch','--list','acceptance/*')) } 'original branch context Delete removes test branch'
    if ((Read-Git @('rev-parse','HEAD')) -ne $startHead -or (Read-Git @('status','--porcelain'))) { throw 'Branch CRUD changed HEAD or worktree' }
    [void](Probe ui-history '' 'cherry-log')
    Wait-Until { (Probe ui-advanced-state '' 'cherry-log') -match 'advancedRow=.*Accept cherry-pick source' } 'cherry-pick source visible in original Log'
    [void](Probe ui-advanced-log-select-cherry '' 'cherry-select')
    [void](Probe ui-advanced-cherry-pick '' 'cherry-pick')
    Wait-Until { (Read-Git @('log','-1','--format=%s')) -eq 'Accept cherry-pick source' } 'original Log Cherry-pick creates commit'
    $pickedHead = Read-Git @('rev-parse','HEAD')
    if ($pickedHead -eq $fixture.cherry -or (Read-Git @('rev-parse','HEAD^')) -ne $startHead -or (Read-Git @('rev-parse','cherry-source')) -ne $fixture.cherry) { throw 'Cherry-pick ancestry or source ref differs' }
    if ((Get-Content (Join-Path $fixture.repository 'cherry.txt') -Raw).Trim() -ne 'Cherry-picked content' -or (Read-Git @('status','--porcelain'))) { throw 'Cherry-pick content or worktree differs' }
    [void](Probe ui-advanced-checkout-feature '' 'rebase-checkout')
    Wait-Until { (Probe ui-advanced-state '' 'rebase-checkout') -match 'currentBranch=rebase-feature' } 'original checkout selects rebase fixture'
    [void](Probe ui-advanced-rebase-open '' 'rebase')
    Wait-Until { (Probe ui-inspect '' 'rebase') -match 'title=Rebase' } 'original Rebase dialog'
    [void](Probe ui-advanced-rebase-target '' 'rebase')
    Wait-Until { (Probe ui-inspect '' 'rebase') -match 'button=Rebase enabled=true' } 'original Rebase accepts selected upstream'
    [void](Probe ui-advanced-rebase '' 'rebase')
    Wait-Until { (Read-Git @('rev-parse','HEAD^')) -eq $fixture.upstream } 'original Rebase replays feature onto upstream'
    if ((Read-Git @('rev-parse','HEAD')) -eq $fixture.feature -or (Read-Git @('log','-1','--format=%s')) -ne 'Replay this feature commit') { throw 'Feature was not rewritten by Rebase' }
    foreach ($entry in @(@('rebase.txt','Feature rebase content'),@('upstream.txt','Upstream rebase content'))) {
        if ((Get-Content (Join-Path $fixture.repository $entry[0]) -Raw).Trim() -ne $entry[1]) { throw 'Rebase file content differs' }
    }
    if (Read-Git @('status','--porcelain')) { throw 'Rebase left dirty worktree' }
    [void](Probe ui-advanced-open-history '' 'blame')
    $blame = Probe api-advanced-blame '' 'blame-provider'
    if (!$blame.Contains('blameRevision.0='+$fixture.base) -or !$blame.Contains('blameRevision.1='+$fixture.history) -or !$blame.Contains('blameRevision.2='+$fixture.base)) { throw 'Original annotation provider returned wrong per-line revisions' }
    $checks.Add('original Git annotation provider maps each line to expected revision')
    [void](Probe ui-advanced-blame '' 'blame')
    Wait-Until { (Probe ui-advanced-state '' 'blame') -match '(?s)blameLine=0 text=.*\bBase\b.*blameLine=1 text=.*\bAuthor\b' } 'original Annotate renders expected abbreviated authors in editor gutter'
    $history = Probe api-advanced-file-history '' 'file-history-provider'
    if (([regex]::Matches($history,'(?m)^fileRevision=')).Count -ne 2 -or !$history.Contains('fileRevision='+$fixture.base) -or !$history.Contains('fileRevision='+$fixture.history)) { throw 'Original file history provider returned wrong revisions' }
    $checks.Add('original file history provider returns both expected commits')
    [void](Probe ui-advanced-file-history '' 'file-history')
    Wait-Until { (Probe ui-advanced-state '' 'file-history') -match '(?s)advancedTable=.*(?:History|history).*rows=2.*Update file history line.*Initialize advanced fixture' } 'original File History displays both commits'
    $log=Get-Content (Join-Path $launch.sandbox 'log\idea.log') -Raw
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe application log errors' }
    $result=[ordered]@{status='passed';archiveSha256=$launch.archiveSha256;evidence=$evidence;fixture=$fixture;checks=$checks.ToArray()}
    $result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 5
} finally {
    $candidate=Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Path -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) { Stop-Process -Id $launch.pid }
}
