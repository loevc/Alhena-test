param([Parameter(Mandatory=$true)][string]$Archive,[Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$repo=(Resolve-Path -LiteralPath $Repository).Path
$fixtureRoot=[IO.Path]::GetFullPath((Join-Path $root 'out/fixtures'))+'\'
if (!$repo.StartsWith($fixtureRoot,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path (Join-Path $repo '.git'))) { throw 'Use an isolated fixture repository' }
$relative='out\workspace-isolation\'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$evidence=Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$baseline=Join-Path $evidence 'metadata-before.json'
& python (Join-Path $PSScriptRoot 'metadata-snapshot.py') capture --repository $repo --snapshot $baseline
if ($LASTEXITCODE) { throw 'Metadata capture failed' }
function Git([string[]]$Arguments) {
    $output=& git.exe -c "safe.directory=$repo" -C $repo @Arguments
    if ($LASTEXITCODE) { throw 'Fixture Git command failed' }
    return ($output -join "`n").Trim()
}
if (Git @('diff','--cached','--name-only')) { throw 'Fixture index must start empty' }
$readme=Join-Path $repo 'README.md'
$original=[IO.File]::ReadAllBytes($readme)
$launch=$null
$checks=[Collections.Generic.List[string]]::new()
function Probe([string]$Stage,[string]$Payload='',[string]$Step=$Stage) {
    return ((& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage $Stage -Payload $Payload -Evidence ($relative+'\'+$Step)) -join "`n")
}
function Wait-Until([scriptblock]$Condition,[string]$Name) {
    $deadline=(Get-Date).AddSeconds(120)
    do {
        if ($launch) {
            $logPath=Join-Path $launch.sandbox 'log/idea.log'
            if ((Test-Path $logPath) -and (Get-Content $logPath -Raw) -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe application error; see recorded sandbox log' }
        }
        if (& $Condition) { $checks.Add($Name); return }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    throw "Timed out: $Name"
}
function Close-Application {
    [void](Probe ui-exit '' 'exit')
    Wait-Until { !(Get-Process -Id $launch.pid -ErrorAction SilentlyContinue) } 'normal platform shutdown'
    $log=Get-Content (Join-Path $launch.sandbox 'log/idea.log') -Raw
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe application log error' }
}
try {
    [IO.File]::AppendAllText($readme,"`nAlhena isolated workspace acceptance.`n")
    & (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
    $sandbox=Join-Path $evidence 'sandbox'
    $launch=(& (Join-Path $root 'run.ps1') -Archive $Archive -Repository $repo -Smoke -Hidden -SandboxDirectory $sandbox) | ConvertFrom-Json
    $launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'launch.json') -Encoding utf8
    Wait-Until {
        $script:snapshot=Probe ui-inspect '' 'workspace'
        $snapshot.Contains('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor') -and $snapshot -match 'table=.*VcsLogMainGraphTable rows=[1-9]'
    } 'central original Log ready'
    if (!$snapshot.Contains('projectStoreClass=alhena.AlhenaProjectStore') -or !$snapshot.Contains('moduleCount=1')) { throw 'Original IDE model was imported' }
    $base=([regex]::Match($snapshot,'(?m)^projectBasePath=(.+)\r?$')).Groups[1].Value.Trim()
    if ([IO.Path]::GetFullPath($base) -ne [IO.Path]::GetFullPath($repo)) { throw 'Repository base path changed' }
    $store=([regex]::Match($snapshot,'(?m)^projectStorePath=(.+)\r?$')).Groups[1].Value.Trim()
    $configRoot=[IO.Path]::GetFullPath((Join-Path $sandbox 'config/repositories'))+'\'
    if (![IO.Path]::GetFullPath($store).StartsWith($configRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Workspace store outside isolated config' }
    $module=([regex]::Match($snapshot,'(?m)^moduleFile=(.+)\r?$')).Groups[1].Value.Trim()
    if ([IO.Path]::GetFullPath($module) -ne [IO.Path]::GetFullPath((Join-Path $store 'repository.iml'))) { throw 'Module file was written into repository' }
    $checks.Add('one plain module and config store outside repository; original base path retained')
    [void](Probe ui-stage-open)
    Wait-Until { (Probe ui-inspect '' 'stage') -match '(?m)^node=\[, Unstaged, .*README.md\]' } 'tracked change visible in original staging UI'
    [void](Probe ui-stage-select "Unstaged`nREADME.md" 'select-stage')
    [void](Probe ui-stage-selected '' 'stage-selected')
    Wait-Until { (Git @('diff','--cached','--name-only')) -eq 'README.md' } 'original selected Stage writes real index'
    Wait-Until { (Probe ui-inspect '' 'stage-refresh') -match '(?m)^node=\[, Staged, .*README.md\]' } 'staged node refreshes'
    [void](Probe ui-stage-select "Staged`nREADME.md" 'select-unstage')
    [void](Probe ui-unstage-selected '' 'unstage-selected')
    Wait-Until { !(Git @('diff','--cached','--name-only')) } 'original selected Unstage preserves worktree'
    if (![IO.File]::ReadAllText($readme).Contains('Alhena isolated workspace acceptance.')) { throw 'Unstage discarded the worktree change' }
    [void](Probe ui-history)
    Close-Application
    $firstHash=$launch.archiveSha256
    $launch=(& (Join-Path $root 'run.ps1') -Archive $Archive -Repository $repo -Smoke -Hidden -SandboxDirectory $sandbox) | ConvertFrom-Json
    Wait-Until { (Probe ui-inspect '' 'reopen').Contains('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor') } 'central workspace restores from external config'
    Close-Application
    & python (Join-Path $PSScriptRoot 'metadata-snapshot.py') verify --repository $repo --snapshot $baseline
    if ($LASTEXITCODE) { throw 'Repository IDE metadata changed' }
    $checks.Add('all original .idea and .iml bytes and file names unchanged after open, stage and reopen')
    $result=[ordered]@{status='passed';archiveSha256=$firstHash;fixture=$repo;evidence=$evidence;metadataBaseline=$baseline;projectStore=$store;moduleFile=$module;checks=$checks.ToArray()}
    $result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 5
} finally {
    if ($launch) {
        $remaining=Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
        if ($remaining -and $remaining.Path -eq (Join-Path $launch.productRoot 'bin/alhena64.exe')) { Stop-Process -Id $launch.pid }
    }
    [void](Git @('reset','--','README.md'))
    [IO.File]::WriteAllBytes($readme,$original)
}
