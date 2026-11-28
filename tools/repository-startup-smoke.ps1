param([Parameter(Mandatory=$true)][string]$Archive, [Parameter(Mandatory=$true)][string]$SourceRepository, [ValidateRange(1,5)][int]$Runs=3)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$source=(Resolve-Path -LiteralPath $SourceRepository).Path
$fixtureRoot=[IO.Path]::GetFullPath((Join-Path $root 'out/fixtures'))+'\'
if (!$source.StartsWith($fixtureRoot,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path (Join-Path $source '.git'))) { throw 'Source must be an isolated fixture repository' }
$relative='out\startup-readiness\'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$evidence=Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
& (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
$records=[Collections.Generic.List[object]]::new()
for ($iteration=1;$iteration -le $Runs;$iteration++) {
    $fixture=Join-Path $fixtureRoot ('workflow-startup-'+(Split-Path $evidence -Leaf)+'-'+$iteration)
    & git.exe -c core.longpaths=true clone --shared $source $fixture
    if ($LASTEXITCODE) { throw 'Fresh fixture clone failed' }
    & git.exe -C $fixture remote remove origin
    if ($LASTEXITCODE -or (Test-Path (Join-Path $fixture '.idea'))) { throw 'Fixture must have no inherited IDE project state' }
    $metadata=Join-Path $evidence ('metadata-before-'+$iteration+'.json')
    & python (Join-Path $PSScriptRoot 'metadata-snapshot.py') capture --repository $fixture --snapshot $metadata | Out-Null
    if ($LASTEXITCODE) { throw 'Cannot capture fixture metadata' }
    $launch=$null
    try {
        $launch=(& (Join-Path $root 'run.ps1') -Archive $Archive -Repository $fixture -Smoke -Hidden) | ConvertFrom-Json
        $launch | ConvertTo-Json | Set-Content (Join-Path $evidence ('launch-'+$iteration+'.json')) -Encoding utf8
        $deadline=(Get-Date).AddSeconds(90)
        do {
            $snapshot=(& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-inspect -Evidence ($relative+'\run-'+$iteration)) -join "`n"
            $log=Join-Path $launch.sandbox 'log/idea.log'
            if ((Test-Path $log) -and (Get-Content $log -Raw) -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe startup error; see recorded launch sandbox' }
            if ($snapshot.Contains('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor') -and ($snapshot -match 'table=.*VcsLogMainGraphTable rows=[1-9]')) { break }
            Start-Sleep -Milliseconds 300
        } while ((Get-Date) -lt $deadline)
        if (!$snapshot.Contains('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor') -or $snapshot -notmatch 'table=.*VcsLogMainGraphTable rows=[1-9]') { throw 'Central Git Log did not become ready' }
        if ([regex]::Matches($snapshot,'(?m)^openFileProtocol=vcs-log\r?$').Count -ne 1) { throw 'Expected one central Log editor' }
        [void](& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-exit -Evidence ($relative+'\exit-'+$iteration))
        $exitDeadline=(Get-Date).AddSeconds(30)
        while (Get-Process -Id $launch.pid -ErrorAction SilentlyContinue) {
            if ((Get-Date) -gt $exitDeadline) { throw 'Platform shutdown timed out' }
            Start-Sleep -Milliseconds 200
        }
        if ((Get-Content $log -Raw) -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe shutdown error' }
        & python (Join-Path $PSScriptRoot 'metadata-snapshot.py') verify --repository $fixture --snapshot $metadata | Out-Null
        if ($LASTEXITCODE) { throw 'Opening a fresh repository created IDE metadata inside it' }
        $records.Add([ordered]@{iteration=$iteration;fixture=$fixture;sandbox=$launch.sandbox;archiveSha256=$launch.archiveSha256;status='passed'})
    } finally {
        if ($launch) {
            $remaining=Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
            if ($remaining -and $remaining.Path -eq (Join-Path $launch.productRoot 'bin/alhena64.exe')) { Stop-Process -Id $launch.pid }
        }
    }
}
$result=[ordered]@{status='passed';archiveSha256=$records[0].archiveSha256;evidence=$evidence;sourceRepository=$source;runs=$records.ToArray();checks=@('fresh repository clone without IDE metadata for each run','central original Log has commits and exactly one editor','no severe startup or shutdown errors','normal platform shutdown','no IDE metadata created or changed inside repository')}
$result | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
$result | ConvertTo-Json -Depth 6
