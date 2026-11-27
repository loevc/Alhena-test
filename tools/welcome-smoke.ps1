param([string]$Archive, [switch]$CommandLine, [switch]$NativeSelection, [string]$FixtureSuffix = '', [switch]$ExistingProject, [string]$RemoteContext, [ValidateSet('https','ssh')][string]$Transport = 'https', [switch]$UnavailableNetwork, [switch]$RejectedAuthentication, [switch]$Reopen, [switch]$SwitchRepositories)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if ($UnavailableNetwork -and (!$RemoteContext -or $Transport -ne 'https')) { throw 'Unavailable network mode requires an HTTPS remote fixture' }
if ($RejectedAuthentication -and (!$RemoteContext -or $Transport -ne 'ssh')) { throw 'Rejected authentication mode requires an SSH remote fixture' }
if ($SwitchRepositories -and (!$NativeSelection -or $RemoteContext)) { throw 'Repository switching requires native open fixture mode' }
if (!$Archive) {
    $artifactRoot = Join-Path $root 'upstream\intellij-community\out\alhena\artifacts'
    $latestArchive = Get-ChildItem -LiteralPath $artifactRoot -Filter 'alhena-*.win.zip' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$latestArchive) { throw 'No built Alhena ZIP found; pass -Archive explicitly' }
    $Archive = $latestArchive.FullName
}
$archiveFile = Get-Item -LiteralPath $Archive
$hash = (Get-FileHash -LiteralPath $archiveFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$evidence = Join-Path $root ('out\welcome-smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$jdk = (Get-ChildItem (Join-Path $root '.cache\bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
$classes = Join-Path $evidence 'classes'
New-Item -ItemType Directory -Path $classes -Force | Out-Null
& (Join-Path $jdk javac.exe) -encoding UTF-8 --add-modules jdk.attach -d $classes (Join-Path $PSScriptRoot 'smoke\Attach.java') (Join-Path $PSScriptRoot 'smoke\WelcomeProbe.java')
if ($LASTEXITCODE) { throw 'Welcome probe compilation failed' }
Set-Content -LiteralPath (Join-Path $evidence 'MANIFEST.MF') -Value 'Agent-Class: WelcomeProbe' -Encoding ascii
$agent = Join-Path $evidence 'welcome-probe.jar'
& (Join-Path $jdk jar.exe) cfm $agent (Join-Path $evidence 'MANIFEST.MF') -C $classes .
if ($LASTEXITCODE) { throw 'Welcome probe packaging failed' }
if ($RemoteContext) {
    if ($CommandLine -or $NativeSelection -or $ExistingProject) { throw 'Clone mode cannot be combined with open modes' }
    $contextFile = [IO.Path]::GetFullPath($RemoteContext)
    $cacheRoot = [IO.Path]::GetFullPath((Join-Path $root '.cache\remote-test')) + '\'
    if (!$contextFile.StartsWith($cacheRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Remote context must be in test cache' }
    $remote = Get-Content -LiteralPath $contextFile -Raw | ConvertFrom-Json
    if ($remote.repository -ne 'loevc/Alhena-test' -or $remote.status -ne 'ready') { throw 'Unauthorized or inactive remote fixture' }
    $fixture = Join-Path $root ('out\fixtures\workflow-remote-' + (Split-Path $evidence -Leaf) + '-' + $Transport)
    if (Test-Path -LiteralPath $fixture) { throw 'Clone target already exists' }
} else {
$fixtureArguments = @((Join-Path $PSScriptRoot 'make-fixture.py'), ('--suffix='+$FixtureSuffix))
if ($ExistingProject) { $fixtureArguments += '--existing-project' }
$previousConsoleEncoding = [Console]::OutputEncoding
$previousPythonEncoding = $env:PYTHONIOENCODING
try {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = 'utf-8'
    $fixture = (& python @fixtureArguments).Trim()
} finally {
    [Console]::OutputEncoding = $previousConsoleEncoding
    $env:PYTHONIOENCODING = $previousPythonEncoding
}
if ($LASTEXITCODE) { throw 'Fixture creation failed' }
if (!(Test-Path -LiteralPath (Join-Path $fixture '.git'))) { throw "Fixture output path cannot be resolved: $fixture" }
}
[IO.File]::WriteAllText((Join-Path $evidence 'fixture.json'), ($fixture | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
if ($NativeSelection) {
    $framework = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319'
    $nativeChooser = Join-Path $evidence 'NativeChooser.exe'
    & (Join-Path $framework 'csc.exe') /nologo /target:exe /platform:x64 ("/out:"+$nativeChooser) ("/reference:"+(Join-Path $framework 'WPF\UIAutomationClient.dll')) ("/reference:"+(Join-Path $framework 'WPF\UIAutomationTypes.dll')) (Join-Path $PSScriptRoot 'smoke\NativeChooser.cs')
    if ($LASTEXITCODE) { throw 'Native chooser driver compilation failed' }
}
$runDirectory = Join-Path $root ('out\run\' + $hash.Substring(0,12))
if (!(Test-Path -LiteralPath (Join-Path $runDirectory '.extracted'))) {
    if (Test-Path -LiteralPath $runDirectory) { throw 'Unmarked extraction directory exists' }
    Expand-Archive -LiteralPath $archiveFile.FullName -DestinationPath $runDirectory
    Set-Content -LiteralPath (Join-Path $runDirectory '.extracted') -Value $hash -Encoding ascii
}
$launcher = Join-Path $runDirectory 'bin\alhena64.exe'
$sandbox = Join-Path $evidence $(if ($CommandLine) { 'cli-sandbox' } else { 'native-sandbox' })
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
$settings = @()
foreach ($name in @('config','system','log','plugins')) {
    $directory = Join-Path $sandbox $name
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $settings += ('idea.' + $name + '.path=' + $directory.Replace('\','/'))
}
$settings += @('idea.initially.ask.config=false','idea.disable.collect.statistics=true','idea.suppress.statistics.report=true')
$properties = Join-Path $sandbox 'alhena.properties'
[IO.File]::WriteAllLines($properties, $settings, (New-Object Text.UTF8Encoding($false)))
if ($CommandLine) {
    # Invoked in the caller's actual shell, including Windows PowerShell 5.1.
    $launchArguments = @{ Repository=$fixture; Hidden=$true; SandboxDirectory=$sandbox }
    if ($PSBoundParameters.ContainsKey('Archive')) { $launchArguments.Archive=$archiveFile.FullName }
    $launch = (& (Join-Path $root 'run.ps1') @launchArguments) | ConvertFrom-Json
    if ($launch.archiveSha256 -ne $hash) { throw 'Launcher selected a different archive' }
    $process = Get-Process -Id $launch.pid
} else {
    $previousProperties = $env:ALHENA_PROPERTIES
    $previousSsh = $env:GIT_SSH_COMMAND
    $savedGitConfig = @{}
    if ($UnavailableNetwork) {
        $gitIndex = if ($env:GIT_CONFIG_COUNT) { [int]$env:GIT_CONFIG_COUNT } else { 0 }
        foreach ($name in @('GIT_CONFIG_COUNT',('GIT_CONFIG_KEY_'+$gitIndex),('GIT_CONFIG_VALUE_'+$gitIndex))) { $savedGitConfig[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
    }
    try {
        $env:ALHENA_PROPERTIES = $properties
        if ($UnavailableNetwork) {
            # Only the test app and its Git children inherit this unreachable proxy.
            [Environment]::SetEnvironmentVariable(('GIT_CONFIG_KEY_'+$gitIndex),'http.proxy','Process')
            [Environment]::SetEnvironmentVariable(('GIT_CONFIG_VALUE_'+$gitIndex),'http://127.0.0.1:9','Process')
            $env:GIT_CONFIG_COUNT = [string]($gitIndex+1)
        }
        if ($RemoteContext -and $Transport -eq 'ssh') {
            foreach ($keyPath in @($remote.privateKeyPath,$remote.knownHostsPath)) {
                $full = [IO.Path]::GetFullPath($keyPath)
                if (!$full.StartsWith($cacheRoot,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $full)) { throw 'Invalid SSH fixture file' }
            }
            $env:GIT_SSH_COMMAND = 'ssh -i "' + $remote.privateKeyPath.Replace('\','/') + '" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="' + $remote.knownHostsPath.Replace('\','/') + '" -o BatchMode=yes'
            if ($RejectedAuthentication) { $env:GIT_SSH_COMMAND += ' -o PubkeyAuthentication=no -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no' }
        }
        # Native entry point, no repository argument and no auto-trust property.
        $process = Start-Process -FilePath $launcher -WorkingDirectory $runDirectory -WindowStyle Hidden -PassThru
    } finally {
        $env:ALHENA_PROPERTIES = $previousProperties; $env:GIT_SSH_COMMAND = $previousSsh
        foreach ($name in $savedGitConfig.Keys) { [Environment]::SetEnvironmentVariable($name,$savedGitConfig[$name],'Process') }
    }
}
function Probe([string]$Operation, [string]$Payload = '') {
    $candidate = Get-Process -Id $process.Id -ErrorAction Stop
    if ($candidate.Path -ne $launcher) { throw 'Unexpected process path' }
    $probeArguments = 'base64:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($evidence+'|'+$Operation+'|'+$Payload))
    & (Join-Path $jdk java.exe) --add-modules jdk.attach -cp $classes Attach $process.Id $agent $probeArguments
    if ($LASTEXITCODE) { throw "Probe failed: $Operation" }
    if (Test-Path -LiteralPath (Join-Path $evidence 'errors.txt')) { throw (Get-Content -LiteralPath (Join-Path $evidence 'errors.txt') -Raw) }
    if ($Operation -eq 'inspect') { return (Get-Content -LiteralPath (Join-Path $evidence 'inspect.txt') -Raw -Encoding utf8) }
}
function Wait-Ui([string]$Pattern) {
    $deadline = (Get-Date).AddSeconds(90)
    do {
        $snapshot = Probe inspect
        if ($snapshot -match $Pattern) { return $snapshot }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "UI timeout: $Pattern; see $evidence"
}
function Save-Ui([string]$Name) {
    Copy-Item -LiteralPath (Join-Path $evidence 'inspect.txt') -Destination (Join-Path $evidence ($Name+'.txt'))
    foreach ($file in Get-ChildItem -LiteralPath $evidence -Filter 'window-*.png') {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $evidence ($Name+'-'+$file.Name))
    }
}
function Wait-Repository([string]$Path,[int]$Rows,[string]$Step) {
    $deadline=(Get-Date).AddSeconds(90)
    do {
        $snapshot=Probe inspect
        if ($snapshot -match 'button=This Window enabled=true') { Save-Ui ($Step+'-window-choice'); Probe this-window }
        elseif ($snapshot -match 'button=Trust[^\r\n]* enabled=true') { Save-Ui ($Step+'-trust'); Probe trust }
        elseif ($snapshot -notmatch 'window=java.awt.FileDialog' -and $snapshot -match 'openProjects=1' -and $snapshot.Contains('project='+$Path.Replace('\','/')) -and $snapshot -match ('(?m)^table=.*VcsLogMainGraphTable rows='+$Rows+'\r?$')) { Save-Ui $Step; return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Repository switch timeout: $Step; see $evidence"
}
function Open-MainRepository([string]$Path,[string]$Step) {
    Probe initial-path $Path
    Probe main-open
    [void](Wait-Ui 'window=java.awt.FileDialog')
    & $nativeChooser $process.Id select $Path (Join-Path $root 'out\fixtures') | Set-Content (Join-Path $evidence ($Step+'-native-selection.txt')) -Encoding utf8
    if ($LASTEXITCODE) { throw 'Main-window native repository confirmation failed' }
}
try {
    if ($RemoteContext) {
        [void](Wait-Ui 'button=Clone Repository enabled=true')
        Probe clone
        [void](Wait-Ui 'title=Clone Repository')
        $url = if ($Transport -eq 'ssh') { $remote.sshUrl } else { $remote.httpsUrl }
        # The original Clone dialog checks out the remote default branch. A new
        # acceptance seed branch does not change that default on an existing repo.
        if (!$UnavailableNetwork -and !$RejectedAuthentication) {
            # This read-only check runs in the harness after its temporary SSH
            # environment was restored. The app still clones using $url and its
            # inherited repo-scoped SSH settings; verify its origin below.
            $advertisedHead = & git.exe ls-remote $remote.httpsUrl HEAD
            if ($LASTEXITCODE -or ($advertisedHead -join "`n") -notmatch '^([0-9a-f]{40})\s+HEAD') { throw 'Cannot resolve remote default HEAD' }
            $expectedRemoteHead = $Matches[1]
        }
        Probe clone-fields ($url+"`n"+$fixture)
        [void](Wait-Ui 'button=Clone enabled=true')
        Save-Ui 'clone-filled'
        Probe clone-go
        if ($UnavailableNetwork -or $RejectedAuthentication) {
            $diagnostic = if ($RejectedAuthentication) { 'Permission denied' } else { 'Failed to connect to 127\.0\.0\.1' }
            $scenario = if ($RejectedAuthentication) { 'SSH authentication rejected with no allowed authentication method' } else { 'unreachable per-process HTTP proxy' }
            $deadline = (Get-Date).AddSeconds(45)
            $failed = $false
            do {
                $logPath = Join-Path $sandbox 'log\idea.log'
                $failureLog = Get-Content -LiteralPath $logPath -Raw -Encoding utf8
                if ($failureLog -match $diagnostic) { $failed = $true; break }
                Start-Sleep -Milliseconds 500
            } while ((Get-Date) -lt $deadline)
            if (!$failed) { throw "Expected clone failure diagnostic was not observed: $diagnostic" }
            [void](Wait-Ui 'button=Clone Repository enabled=true')
            if (Test-Path -LiteralPath (Join-Path $fixture '.git')) { throw 'Failed clone left a repository' }
            Save-Ui 'network-failure'
            $result = [ordered]@{status='passed';archiveSha256=$hash;evidence=$evidence;fixture=$fixture;remote=$url;transport=$Transport;scenario=$scenario;checks=@('original Clone reports expected failure diagnostic','welcome UI remains usable','no cloned repository left behind','no global network or authentication configuration changed')}
            $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'result.json') -Encoding utf8
            $result | ConvertTo-Json -Depth 5
            return
        }
    } elseif (!$CommandLine) {
    [void](Wait-Ui 'button=Open Repository enabled=true')
    if ($NativeSelection) { Probe initial-path $fixture; Start-Sleep -Milliseconds 200 }
    Probe open
    [void](Wait-Ui 'window=java.awt.FileDialog')
    Save-Ui 'native-chooser'
    if ($NativeSelection) {
        & $nativeChooser $process.Id inspect | Set-Content -LiteralPath (Join-Path $evidence 'native-controls.txt') -Encoding utf8
        if ($LASTEXITCODE) { throw 'Native chooser inspection failed' }
        & $nativeChooser $process.Id select $fixture (Join-Path $root 'out\fixtures') | Set-Content -LiteralPath (Join-Path $evidence 'native-selection.txt') -Encoding utf8
        if ($LASTEXITCODE) { throw 'Native chooser selection failed' }
    } else {
    Probe cancel
    [void](Wait-Ui 'button=Open Repository enabled=true')
    Probe clone
    [void](Wait-Ui '(?i)title=.*(?:version control|clone)')
    Save-Ui 'clone-dialog'
    Probe cancel
    Probe ide-chooser
    Start-Sleep -Milliseconds 250
    Probe open
    [void](Wait-Ui 'chooserDirectory=')
    Probe path $fixture
    [void](Wait-Ui ('chooserDirectory='+[regex]::Escape($fixture)))
    Save-Ui 'selected-repository'
    Probe choose
    }
    }
    $trust = $false
    $deadline = (Get-Date).AddSeconds(90)
    do {
        $snapshot = Probe inspect
        if ($snapshot -match 'button=Trust[^\r\n]* enabled=true') { Save-Ui 'trust-dialog'; Probe trust; $trust=$true; break }
        if ($snapshot -match 'openProjects=1') { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    $rowCount = if ($RemoteContext) { '(?:[5-9]|[1-9][0-9]+)' } else { '5' }
    $opened = Wait-Ui ('(?m)^table=com.intellij.vcs.log.ui.(?:table.VcsLogGraphTable|frame.VcsLogMainGraphTable) rows='+$rowCount+'\r?$')
    if (!$opened.Contains('project='+$fixture.Replace('\','/')) -and !$opened.Contains('project='+$fixture)) { throw 'Wrong project opened' }
    Save-Ui 'opened-history'
    if ($Reopen) {
        if ($RemoteContext) { throw 'Reopen mode requires an open fixture' }
        Probe close
        Wait-Process -Id $process.Id -Timeout 15 -ErrorAction Stop
        $previousProperties = $env:ALHENA_PROPERTIES
        try {
            $env:ALHENA_PROPERTIES = $properties
            $process = Start-Process -FilePath $launcher -WorkingDirectory $runDirectory -ArgumentList ('"'+$fixture+'"') -WindowStyle Hidden -PassThru
        } finally { $env:ALHENA_PROPERTIES = $previousProperties }
        $reopened = Wait-Ui ('(?m)^table=com.intellij.vcs.log.ui.(?:table.VcsLogGraphTable|frame.VcsLogMainGraphTable) rows=5\r?$')
        if (!$reopened.Contains('project='+$fixture.Replace('\','/')) -or $reopened -notmatch 'openProjects=1') { throw 'Reopened wrong project or duplicate project' }
        Save-Ui 'reopened-history'
    }
    if ($SwitchRepositories) {
        # Original toolbar control and actual native Cancel, scoped to this PID.
        Probe initial-path $fixture
        Probe main-open
        [void](Wait-Ui 'window=java.awt.FileDialog')
        & $nativeChooser $process.Id cancel | Set-Content (Join-Path $evidence 'main-open-native-cancel.txt') -Encoding utf8
        if ($LASTEXITCODE) { throw 'Native cancellation failed' }
        Wait-Repository $fixture 5 'main-open-cancelled'
        Open-MainRepository $fixture 'same-repository'
        Wait-Repository $fixture 5 'same-repository'
        $previousConsoleEncoding=[Console]::OutputEncoding
        $previousPythonEncoding=$env:PYTHONIOENCODING
        try {
            [Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
            $env:PYTHONIOENCODING='utf-8'
            $secondFixture=(& python (Join-Path $PSScriptRoot 'make-fixture.py') ('--suffix= switch'+$FixtureSuffix) --existing-project).Trim()
        } finally {
            [Console]::OutputEncoding=$previousConsoleEncoding
            $env:PYTHONIOENCODING=$previousPythonEncoding
        }
        if ($LASTEXITCODE -or !(Test-Path -LiteralPath (Join-Path $secondFixture '.git'))) { throw 'Second switch fixture failed' }
        [IO.File]::WriteAllText((Join-Path $secondFixture 'switch-marker.txt'),"Second repository switch marker`n")
        & git -C $secondFixture add switch-marker.txt
        if ($LASTEXITCODE) { throw 'Switch marker staging failed' }
        & git -C $secondFixture -c 'user.name=Alhena Switch Fixture' -c 'user.email=fixture@example.invalid' commit -m 'Second repository switch marker' | Out-Null
        if ($LASTEXITCODE) { throw 'Switch marker commit failed' }
        Open-MainRepository $secondFixture 'second-repository'
        Wait-Repository $secondFixture 6 'second-repository'
        Open-MainRepository $fixture 'return-to-first'
        Wait-Repository $fixture 5 'return-to-first'
    }
    $log = Get-Content -LiteralPath (Join-Path $sandbox 'log\idea.log') -Raw -Encoding utf8
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Welcome actions produced severe log entries' }
    $checks = @('repository opens and displays Git history','no automatic trust bypass','no SEVERE/ERROR log entries')
    if ($Reopen) { $checks += 'same repository reopens with its persisted Git workspace and one project' }
    if ($SwitchRepositories) { $checks += @('real main-toolbar Open control and native Cancel preserve current repository','selecting same repository keeps exactly one open project','main-toolbar native selection switches to second existing IDEA repository with six commits','switching back restores first repository and five commits') }
    if ($CommandLine) { $checks += 'run.ps1 -Repository executed in actual caller PowerShell' }
    elseif ($RemoteContext) {
        $origin = & git -c "safe.directory=$fixture" -C $fixture remote get-url origin
        if ($LASTEXITCODE -or $origin -ne $url) { throw 'Clone origin mismatch' }
        $head = & git -c "safe.directory=$fixture" -C $fixture rev-parse HEAD
        if ($LASTEXITCODE -or $head -ne $expectedRemoteHead) { throw 'Cloned default HEAD mismatch' }
        $checks += ('real original Clone Repository dialog completed via ' + $Transport)
    }
    elseif ($NativeSelection) { $checks += @('native EXE without repository argument','real Windows native chooser selects and confirms repository') }
    else { $checks += @('native EXE without repository argument','real welcome button opens Windows native chooser','real Clone Repository button opens upstream dialog','original IDE chooser selects fixture directory') }
    $result = [ordered]@{status='passed';archiveSha256=$hash;evidence=$evidence;fixture=$fixture;powerShellVersion=$PSVersionTable.PSVersion.ToString();commandLineMode=[bool]$CommandLine;nativeSelection=[bool]$NativeSelection;existingProject=[bool]$ExistingProject;trustConfirmationObserved=$trust;checks=$checks}
    if ($RemoteContext) { $result.remote = $url; $result.transport = $Transport; $result.head = $head }
    if ($SwitchRepositories) { $result.secondFixture=$secondFixture; $result.repositorySwitching=$true }
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 5
} finally {
    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        try { Probe close; Wait-Process -Id $process.Id -Timeout 15 -ErrorAction SilentlyContinue } catch { }
        $candidate = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        if ($candidate -and $candidate.Path -eq $launcher) { Stop-Process -Id $process.Id }
    }
}
