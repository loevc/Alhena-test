param([string]$Archive)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$archiveArgument = @{}
if ($Archive) { $archiveArgument.Archive = $Archive }
& (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
$fixture = (& python (Join-Path $PSScriptRoot 'make-workflow-fixture.py')) | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Fixture failed' }
$relative = 'out\workspace-git-smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$evidence = Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$launch = (& (Join-Path $root 'run.ps1') @archiveArgument -Repository $fixture.repository -Smoke -Hidden) | ConvertFrom-Json
$checks = [Collections.Generic.List[string]]::new()
$launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'launch.json') -Encoding utf8
function Read-Git([string[]]$Arguments) {
    $value = & git.exe -C $fixture.repository @Arguments
    if ($LASTEXITCODE) { throw "Git validation failed: $($Arguments[0])" }
    return ($value -join "`n").Trim()
}
function Probe([string]$Stage, [string]$Payload = '', [string]$Step = $Stage) {
    (& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage $Stage -Payload $Payload -Evidence ($relative+'\'+$Step)) -join "`n"
}
function Wait-Until([scriptblock]$Condition, [string]$Name) {
    $deadline = (Get-Date).AddSeconds(40)
    do {
        if (& $Condition) { $checks.Add($Name); Write-Output "PASS $Name"; return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Timed out: $Name; see $evidence"
}
try {
    Wait-Until {
        $log = Join-Path $launch.sandbox 'log\idea.log'
        (Test-Path $log) -and ((Get-Content $log -Raw) -match 'Git version for ')
    } 'native Git ready'
    Wait-Until { (Probe ui-inspect '' 'central-history') -match 'selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor' } 'original Git Log occupies selected central editor'
    for ($index=0;$index -lt 3;$index++) { [void](Probe ui-history '' 'history-reuse') }
    $snapshot = Probe ui-inspect '' 'history-reuse'
    if (([regex]::Matches($snapshot,'(?m)^openFileProtocol=vcs-log\r?$')).Count -ne 1) { throw 'History action created duplicate editor tabs' }
    if ($snapshot -match 'toolWindow=Version Control visible=true') { throw 'Duplicate bottom Git Log left visible' }
    $checks.Add('History reuses one original central log editor')
    [void](Probe ui-git-settings '' 'git-settings')
    Wait-Until { (Probe ui-inspect '' 'git-settings') -match 'label=.*Git executable' } 'Git Settings opens original Git executable settings directly'
    [void](Probe ui-click 'Cancel' 'git-settings-close')
    Wait-Until { (Probe ui-inspect '' 'git-settings-closed') -notmatch 'title=Settings' } 'Git settings cancel returns to repository'
    [void](Probe ui-stage-open)
    Wait-Until { (Probe ui-inspect '' 'unstaged') -match 'GitStagePanel.*' } 'original staging panel opens alongside central history'
    [void](Probe ui-stage-all)
    Wait-Until { (Probe ui-inspect '' 'staged') -match '(?m)^node=\[, Staged, .*README.md\]' } 'Stage All refreshes original tree'
    [void](Probe ui-stage-select "Staged`nREADME.md" 'unstage')
    [void](Probe ui-unstage-selected '' 'unstage')
    Wait-Until { (Read-Git @('diff','--cached','--name-only')) -eq 'new-file.txt' } 'original selected Unstage preserves other staged file'
    if ((Get-Content (Join-Path $fixture.repository 'README.md') -Raw) -notmatch 'Commit through') { throw 'Unstage lost working content' }
    Wait-Until { (Probe ui-inspect '' 'discard') -match '(?m)^node=\[, Unstaged, .*README.md\]' } 'unstaged file refreshes in UI'
    [void](Probe ui-stage-select "Unstaged`nREADME.md" 'discard')
    [void](Probe ui-discard-selected '' 'discard')
    Wait-Until { !(Read-Git @('diff','--name-only')) } 'original selected Discard restores working file'
    if ((Read-Git @('diff','--cached','--name-only')) -ne 'new-file.txt') { throw 'Discard changed unrelated staged file' }
    [void](Probe ui-stash-open '' 'stash')
    Wait-Until { (Probe ui-inspect '' 'stash') -match 'button=Create Stash enabled=true' } 'original Stash dialog'
    [void](Probe ui-message 'Alhena stash acceptance' 'stash')
    [void](Probe ui-stash '' 'stash')
    Wait-Until { (Read-Git @('stash','list')) -match 'Alhena stash acceptance' } 'original Stash saves staged change'
    if (Read-Git @('status','--porcelain')) { throw 'Stash did not clean fixture worktree' }
    Wait-Until { (Probe ui-inspect '' 'stash-tracker') -match '(?s)stashCount=1.*tab=Stash' } 'original stash tracker and tab are ready for Unstash'
    [void](Probe ui-unstash-open '' 'unstash')
    Wait-Until { (Probe ui-inspect '' 'unstash') -match '(?s)SavedPatchesTree.*Alhena stash acceptance.*button=Apply enabled=true' } 'original stash browser loads saved entry'
    [void](Probe ui-unstash '' 'unstash')
    Wait-Until { Test-Path (Join-Path $fixture.repository 'new-file.txt') } 'original Apply Stash restores file'
    if ((Get-Content (Join-Path $fixture.repository 'new-file.txt') -Raw).Trim() -ne 'Stage untracked files too.') { throw 'Restored stash content differs' }
    $sandbox = $launch.sandbox
    [void](Probe ui-exit '' 'restart')
    Wait-Process -Id $launch.pid -Timeout 15 -ErrorAction Stop
    $launch = (& (Join-Path $root 'run.ps1') @archiveArgument -Repository $fixture.repository -Smoke -Hidden -SandboxDirectory $sandbox) | ConvertFrom-Json
    $launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'relaunch.json') -Encoding utf8
    Wait-Until { (Probe ui-inspect '' 'restored-history') -match 'selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor' } 'central Git Log restores after normal platform exit'
    [void](Probe ui-history '' 'restored-history')
    if (([regex]::Matches((Probe ui-inspect '' 'restored-history'),'(?m)^openFileProtocol=vcs-log\r?$')).Count -ne 1) { throw 'Restored history duplicated' }
    $log = Get-Content (Join-Path $launch.sandbox 'log\idea.log') -Raw
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe application log errors' }
    $result = [ordered]@{status='passed';archiveSha256=$launch.archiveSha256;evidence=$evidence;fixture=$fixture;checks=$checks.ToArray()}
    $result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 5
} finally {
    $candidate = Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Path -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) { Stop-Process -Id $launch.pid }
}
