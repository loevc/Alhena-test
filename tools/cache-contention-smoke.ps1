param([Parameter(Mandatory=$true)][string]$Archive)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$relative='out/cache-contention/'+(Get-Date -Format yyyyMMdd-HHmmss)
$evidence=Join-Path $root $relative
$classes=Join-Path $evidence classes
New-Item -ItemType Directory -Path $classes -Force | Out-Null
$jdk=(Get-ChildItem (Join-Path $root '.cache/bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
& (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
& (Join-Path $jdk javac.exe) -encoding UTF-8 --add-modules jdk.attach -d $classes (Join-Path $PSScriptRoot 'smoke/CacheSaveProbe.java') (Join-Path $PSScriptRoot 'smoke/Attach.java')
if($LASTEXITCODE){throw 'Cache probe compilation failed'}
$manifest=Join-Path $evidence MANIFEST.MF
Set-Content $manifest -Value 'Agent-Class: CacheSaveProbe' -Encoding ascii
$agent=Join-Path $evidence cache-probe.jar
& (Join-Path $jdk jar.exe) cfm $agent $manifest -C $classes .
if($LASTEXITCODE){throw 'Cache probe packaging failed'}
$fixture=(& python (Join-Path $PSScriptRoot 'make-workflow-fixture.py')) | ConvertFrom-Json
if($LASTEXITCODE){throw 'Fixture creation failed'}
$launch=$null
$result=[ordered]@{status='failed';evidence=$evidence;checks=@()}
try {
    $launch=(& (Join-Path $root run.ps1) -Archive $Archive -Repository $fixture.repository -Smoke -Hidden -SandboxDirectory (Join-Path $evidence sandbox)) | ConvertFrom-Json
    $result.archiveSha256=$launch.archiveSha256
    $result.fixture=$fixture.repository
    $launch | ConvertTo-Json | Set-Content (Join-Path $evidence launch.json) -Encoding utf8
    $deadline=(Get-Date).AddSeconds(45)
    do {
        $snapshot=(& (Join-Path $PSScriptRoot workflow-probe.ps1) -Stage ui-inspect -Evidence ($relative+'/ready')) -join "`n"
        if($snapshot.Contains('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor')){break}
        Start-Sleep -Milliseconds 300
    } while((Get-Date)-lt$deadline)
    if(!$snapshot.Contains('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor')){throw 'Original Log editor not ready'}
    & (Join-Path $jdk java.exe) --add-modules jdk.attach -cp $classes Attach $launch.pid $agent ($root+'|'+$fixture.repository+'|'+(Join-Path $launch.sandbox system)+'|'+$evidence)
    if($LASTEXITCODE){throw 'Cache probe attach failed'}
    $probe=Get-Content (Join-Path $evidence cache-probe.txt) -Raw
    if(!$probe.Contains('cacheProbePassed=true')){throw 'Original cache contention test failed; inspect cache-probe.txt'}
    $result.checks=@('original cache service and owned sandbox guard','20/40/60ms read contention recovers and cache deserializes','persistent denial bounded and visible','old cache bytes preserved on failure','interruption exits retry and preserves thread flag','all temporary files cleaned','100 unheld saves and final deserialize')
    $result.status='passed'
} catch {
    $result.error=$_.Exception.Message
    throw
} finally {
    if($launch){
        try {
            $remaining=Get-CimInstance Win32_Process -Filter ('ProcessId='+$launch.pid)
            if($remaining -and $remaining.ExecutablePath -eq (Join-Path $launch.productRoot bin/alhena64.exe)){
                [void](& (Join-Path $PSScriptRoot workflow-probe.ps1) -Stage ui-exit -Evidence ($relative+'/exit'))
                $deadline=(Get-Date).AddSeconds(30)
                while(Get-Process -Id $launch.pid -ErrorAction SilentlyContinue){if((Get-Date)-gt$deadline){throw 'Normal cache-test shutdown timed out'};Start-Sleep -Milliseconds 200}
            }
            $log=Get-Content (Join-Path $launch.sandbox log/idea.log) -Raw
            if($log -match '\] (?:SEVERE|\s*ERROR) - '){throw 'Severe application log during cache test'}
            $result.normalExit=$true
        } catch {
            $result.status='failed';$result.shutdownError=$_.Exception.Message
            throw
        } finally {
            $remaining=Get-CimInstance Win32_Process -Filter ('ProcessId='+$launch.pid)
            if($remaining -and $remaining.ExecutablePath -eq (Join-Path $launch.productRoot bin/alhena64.exe)){Stop-Process -Id $launch.pid -ErrorAction SilentlyContinue}
            $result | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $evidence result.json) -Encoding utf8
        }
    }
}
$result | ConvertTo-Json -Depth 4
