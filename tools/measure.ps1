param([Parameter(Mandatory=$true)][string]$Archive, [Parameter(Mandatory=$true)][string]$Label, [ValidateRange(3,10)][int]$Runs = 3, [string]$Repository, [ValidateRange(60,900)][int]$WaitSeconds=180)
$ErrorActionPreference = 'Stop'
if ($Label -notmatch '^[a-zA-Z0-9_-]+$') { throw '测量标签仅允许字母、数字、下划线和连字符' }
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root ('out\measurements\' + $Label + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$classes = Join-Path $directory 'classes'
New-Item -ItemType Directory -Path $classes -Force | Out-Null
$jdk = (Get-ChildItem (Join-Path $root '.cache\bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
& (Join-Path $jdk javac.exe) -encoding UTF-8 --add-modules jdk.attach -d $classes (Join-Path $PSScriptRoot 'smoke\Attach.java') (Join-Path $PSScriptRoot 'smoke\UiProbe.java')
if ($LASTEXITCODE) { throw '测量探针编译失败' }
$manifest = Join-Path $directory 'MANIFEST.MF'
Set-Content -LiteralPath $manifest -Value 'Agent-Class: UiProbe' -Encoding ascii
$agent = Join-Path $directory 'probe.jar'
& (Join-Path $jdk jar.exe) cfm $agent $manifest -C $classes .
if ($LASTEXITCODE) { throw '测量探针打包失败' }
if ($Repository) {
    $fixture = (Resolve-Path -LiteralPath $Repository).Path
    $fixtureRoot = [IO.Path]::GetFullPath((Join-Path $root 'out\fixtures')) + '\'
    if (!$fixture.StartsWith($fixtureRoot,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath (Join-Path $fixture '.git'))) { throw 'Measurement repository must be an isolated fixture' }
} else {
    $fixture = & python (Join-Path $PSScriptRoot 'make-fixture.py')
    if ($LASTEXITCODE) { throw '测量仓库创建失败' }
}
$commitCount = & git -c "safe.directory=$fixture" -C $fixture rev-list --count HEAD
if ($LASTEXITCODE) { throw 'Cannot count fixture commits' }
$trackedFiles = @(& git -c "safe.directory=$fixture" -C $fixture ls-files)
if ($LASTEXITCODE) { throw 'Cannot count fixture files' }
$repositoryHead = & git -c "safe.directory=$fixture" -C $fixture rev-parse HEAD
if ($LASTEXITCODE) { throw 'Cannot read fixture HEAD' }
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$machine = [ordered]@{ os=$os.Caption; osVersion=$os.Version; cpu=$cpu.Name; logicalProcessors=$cpu.NumberOfLogicalProcessors; physicalMemoryBytes=[long]$os.TotalVisibleMemorySize*1024; upstream=(Get-Content (Join-Path $root 'upstream.lock.json') -Raw | ConvertFrom-Json).commit; repository=$fixture; repositoryHead=$repositoryHead; commits=[int]$commitCount; files=$trackedFiles.Count; runs=$Runs; waitSeconds=$WaitSeconds; method='Instrumented Swing readiness, no forced GC; graceful platform exit saves settings and VFS between cached launches. Fresh application config is not cold OS cache. Includes attach/poll overhead. Stable samples require no scanner/queued scan, no dumb mode, no visible progress and unchanged scanner start/stop event count across two observations. Log readiness requires rows in the selected central editor, not another visible graph.' }
$machine | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'machine.json') -Encoding utf8
$samples = [Collections.Generic.List[object]]::new()
$launch = $null

function Snapshot([string]$Stage='inspect') {
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $launch.pid)
    if (!$process -or $process.ExecutablePath -ne (Join-Path $launch.productRoot 'bin\alhena64.exe')) { throw '测量进程路径不匹配' }
    & (Join-Path $jdk java.exe) --add-modules jdk.attach -cp $classes Attach $launch.pid $agent ($sampleDirectory + '|' + $Stage)
    if ($LASTEXITCODE) { throw '测量探针失败' }
    $snapshot = Get-Content -LiteralPath (Join-Path $sampleDirectory ($Stage+'.txt')) -Raw
    if ($snapshot -match '(?m)^.*(?:Exception|Error):') { throw '测量探针返回异常' }
    return $snapshot
}
function Await-Snapshot([string]$Pattern, [string]$Stage='inspect') {
    $deadline=(Get-Date).AddSeconds($WaitSeconds)
    do {
        $snapshot=Snapshot $Stage
        if($snapshot -match $Pattern) { return $snapshot }
        Start-Sleep -Milliseconds 300
    } while((Get-Date) -lt $deadline)
    throw "测量等待超时：$Pattern"
}
function Await-StableSnapshot {
    $deadline=(Get-Date).AddSeconds($WaitSeconds)
    $previous=$null
    $idlePattern=if($scenario -eq 'empty-fresh') { '(?m)^metric.runningProgressIndicators=0' } else { '(?s)\A(?=.*metric.runningProgressIndicators=0)(?=.*metric.projectDumb=false)(?=.*metric.projectScanning=false)(?=.*metric.scanningQueued=false)' }
    do {
        $value=Snapshot
        if($value -match $idlePattern) {
            $counter=([regex]::Match($value,'(?m)^metric.scanningActivity=(\d+)')).Groups[1].Value
            if($null -ne $previous -and $previous -eq $counter) { return $value }
            $previous=$counter
        } else { $previous=$null }
        Start-Sleep -Milliseconds 500
    } while((Get-Date) -lt $deadline)
    throw 'Scanner/indexing did not become stable within the configured measurement window'
}
function Stop-Sample {
    if($launch) {
        $process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$launch.pid)
        if($process -and $process.ExecutablePath -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) {
            try { [void](Snapshot 'close') } catch { Write-Output '平台退出请求未正常返回，正在检查进程状态。' }
            $deadline=(Get-Date).AddSeconds(20)
            do {
                $remaining=Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
                if(!$remaining) {
                    $exitLog=Join-Path $launch.sandbox 'log\idea.log'
                    if((Get-Content -LiteralPath $exitLog -Raw) -match '\] (?:SEVERE|\s*ERROR) - ') { throw '平台退出日志出现严重错误，样本无效' }
                    return
                }
                Start-Sleep -Milliseconds 200
            } while((Get-Date) -lt $deadline)
            Stop-Process -Id $launch.pid
            throw '平台未正常完成退出；已关闭自有测试进程，本次数据不作为缓存启动样本'
        }
    }
}
function Read-Metrics([string]$SnapshotText) {
    $metrics=@{}
    foreach($match in [regex]::Matches($SnapshotText,'(?m)^metric\.(\w+)=(\d+)')) { $metrics[$match.Groups[1].Value]=[long]$match.Groups[2].Value }
    if(!$metrics.ContainsKey('heapUsedBytes')) { throw '未读到 JVM heap，不能记录有效样本' }
    return $metrics
}
$scenarios = if ($Repository) { @('repository-fresh','repository-cached') } else { @('empty-fresh','repository-fresh','repository-cached') }
foreach($scenario in $scenarios) {
    # First cached launch is recorded as warmup, then excluded from summary.
    $iterations=if($scenario -eq 'repository-cached') { 0..$Runs } else { 1..$Runs }
    foreach($iteration in $iterations) {
        $sampleDirectory=Join-Path $directory ($scenario+'-'+$iteration)
        $sandbox=if($scenario -eq 'repository-cached') { Join-Path $directory 'cached-config' } else { Join-Path $sampleDirectory 'sandbox' }
        $options=@{ Archive=$Archive; SandboxDirectory=$sandbox; Hidden=$true }
        if($scenario -ne 'empty-fresh') { $options.Repository=$fixture; $options.Smoke=$true }
        try {
            $launch=(& (Join-Path $root 'run.ps1') @options) | ConvertFrom-Json
            New-Item -ItemType Directory -Path $sampleDirectory -Force | Out-Null
            $launch | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $sampleDirectory 'launch.json') -Encoding utf8
            $started=[DateTimeOffset]::Parse($launch.started)
            $frameSnapshot=Await-Snapshot 'window=.*visible=true size=java.awt.Dimension\[width=[1-9][0-9]{2,}'
            $frameMs=([DateTimeOffset]::Now-$started).TotalMilliseconds
            $frameWorkingSet=(Get-Process -Id $launch.pid).WorkingSet64
            $frameMetrics=Read-Metrics $frameSnapshot
            $logMs=$null
            $logWorkingSet=$null
            $logHeap=$null
            $indexSettledMs=$null
            $diffReadyMs=$null
            if($scenario -ne 'empty-fresh') {
                # Require a populated visible graph inside the selected central editor;
                # a ready bottom tool-window graph is not sufficient.
                $logSnapshot=Await-Snapshot '(?m)^metric.centralLogRows=[1-9][0-9]*' 'activate'
                $logMs=([DateTimeOffset]::Now-$started).TotalMilliseconds
                $logWorkingSet=(Get-Process -Id $launch.pid).WorkingSet64
                $logHeap=(Read-Metrics $logSnapshot).heapUsedBytes
                $initialIndexSnapshot=Await-StableSnapshot
                $initialScanActivity=([regex]::Match($initialIndexSnapshot,'(?m)^metric.scanningActivity=(\d+)')).Groups[1].Value
                $indexSettledMs=([DateTimeOffset]::Now-$started).TotalMilliseconds
                $diffStarted=[DateTimeOffset]::Now
                [void](Snapshot 'select')
                [void](Await-Snapshot 'canShowDiff=true' 'diff')
                [void](Await-Snapshot 'diffComponent=.*Twoside')
                $diffReadyMs=([DateTimeOffset]::Now-$diffStarted).TotalMilliseconds
            }
            # Give startup activities time to settle. This is a sampled idle point,
            # not a promise that every background timer has stopped forever.
            Start-Sleep -Seconds 5
            $snapshot=Await-StableSnapshot
            $finalScanActivity=([regex]::Match($snapshot,'(?m)^metric.scanningActivity=(\d+)')).Groups[1].Value
            if($scenario -ne 'empty-fresh' -and $finalScanActivity -ne $initialScanActivity) {
                $indexSettledMs=([DateTimeOffset]::Now-$started).TotalMilliseconds
            }
            $metrics=Read-Metrics $snapshot
            $logPath=Join-Path $launch.sandbox 'log\idea.log'
            if((Test-Path -LiteralPath $logPath) -and ((Get-Content -LiteralPath $logPath -Raw) -match '\] (?:SEVERE|\s*ERROR) - ')) { throw "测量日志存在严重错误：$logPath" }
            if((Get-Content -LiteralPath $logPath -Raw).Contains('NOT_CLOSED_PROPERLY')) { throw '检测到 VFS 崩溃恢复，不能作为正常缓存启动样本' }
            $process=Get-Process -Id $launch.pid
            $sample=[ordered]@{ scenario=$scenario; iteration=$iteration; warmup=($iteration -eq 0); archiveSha256=$launch.archiveSha256; frameReadyMs=[math]::Round($frameMs); frameWorkingSetBytes=$frameWorkingSet; frameHeapUsedBytes=$frameMetrics.heapUsedBytes; gitLogReadyMs=$(if($null -ne $logMs){[math]::Round($logMs)}else{$null}); gitLogWorkingSetBytes=$logWorkingSet; gitLogHeapUsedBytes=$logHeap; indexSettledMs=$(if($null -ne $indexSettledMs){[math]::Round($indexSettledMs)}else{$null}); diffReadyMs=$(if($null -ne $diffReadyMs){[math]::Round($diffReadyMs)}else{$null}); sampledAtMs=[math]::Round(([DateTimeOffset]::Now-$started).TotalMilliseconds); workingSetBytes=$process.WorkingSet64; privateBytes=$process.PrivateMemorySize64; heapUsedBytes=$metrics.heapUsedBytes; heapCommittedBytes=$metrics.heapCommittedBytes; loadedClasses=$metrics.loadedClasses; runningProgressIndicators=$metrics.runningProgressIndicators; evidence=$sampleDirectory }
            $samples.Add($sample)
            $sample | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $sampleDirectory 'sample.json') -Encoding utf8
            Write-Output ("{0} #{1}: frame={2}ms log={3}ms workingSet={4:N1}MiB heap={5:N1}MiB" -f $scenario,$iteration,$sample.frameReadyMs,$sample.gitLogReadyMs,($sample.workingSetBytes/1MB),($sample.heapUsedBytes/1MB))
        } finally { Stop-Sample; $launch=$null }
        $sample['shutdownClean']=$true
        $sample | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $sampleDirectory 'sample.json') -Encoding utf8
    }
}
$result=[ordered]@{ label=$Label; machine=$machine; samples=$samples.ToArray() }
$result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $directory 'results.json') -Encoding utf8
Write-Output "测量完成：$directory\results.json"
