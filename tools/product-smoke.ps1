param([string]$Archive)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$archiveArgument = @{}
if ($Archive) { $archiveArgument.Archive = $Archive }
$relative = 'out\product-smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$evidence = Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
& (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
$fixture = (& python (Join-Path $PSScriptRoot 'make-workflow-fixture.py')) | ConvertFrom-Json
if($LASTEXITCODE) { throw '专用测试仓库创建失败' }
$launch=$null
function Stop-Test {
    if($launch) {
        $candidate=Get-CimInstance Win32_Process -Filter ('ProcessId='+$launch.pid)
        if($candidate -and $candidate.ExecutablePath -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) { Stop-Process -Id $launch.pid }
    }
}
function Check-Log {
    $log=Get-Content -LiteralPath (Join-Path $launch.sandbox 'log\idea.log') -Raw
    if($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw "产品启动出现严重错误：$($launch.sandbox)" }
}
try {
    $launch=(& (Join-Path $root 'run.ps1') @archiveArgument -Repository $fixture.repository -Smoke -Hidden -FirstLaunch -SandboxDirectory (Join-Path $evidence 'native-project')) | ConvertFrom-Json
    $launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'project-launch.json') -Encoding utf8
    $deadline=(Get-Date).AddSeconds(35)
    do {
        $log=Join-Path $launch.sandbox 'log\idea.log'
        if((Test-Path $log) -and ((Get-Content $log -Raw) -match 'Git version for ')) { break }
        Start-Sleep -Milliseconds 400
    } while((Get-Date) -lt $deadline)
    do {
        $snapshot=(& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-inspect -Evidence ($relative+'\project')) -join "`n"
        if($snapshot -match 'selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor' -and $snapshot -match 'commitMode=GitStagingAreaCommitMode') { break }
        Start-Sleep -Milliseconds 400
    } while((Get-Date) -lt $deadline)
    foreach($expected in @('selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor','toolWindow=Version Control visible=false','commitMode=GitStagingAreaCommitMode','updates.platform=false plugins=false','usageStatisticsAllowed=false provider=alhena.AlhenaConsent')) {
        if(!$snapshot.Contains($expected)) { throw "产品默认状态不符合预期：$expected" }
    }
    foreach($action in @('OpenFile','Alhena.History','Git.Commit.Stage','Git.Fetch','Vcs.UpdateProject','Vcs.Push','Alhena.GitSettings')) {
        if(!$snapshot.Contains('actionChild.Alhena.GitToolbar='+$action)) { throw "Git 工具栏缺失：$action" }
    }
    if($snapshot -match 'actionChild.MainMenu=(?:CodeMenu|AnalyzeMenu|RefactoringMenu|BuildMenu|RunMenu)' -or $snapshot -match 'actionChild.MainToolbarRight=(?:NewUiRunWidget|ExecutionTargetsToolbarGroup|StopWithDropDown)') { throw '无关 IDE 主入口未移除' }
    foreach($id in @('TODO','Services','Bookmarks','Problems View','Structure','Meet New UI')) {
        if($snapshot -match ('toolWindow='+[regex]::Escape($id)+' visible=\w+ available=true')) { throw "无关工具窗口仍然可用：$id" }
    }
    $fileTypes=(& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-filetype-policy -Evidence ($relative+'\file-types')) -join "`n"
    if (!$fileTypes.Contains('sourceFileTypePolicyVerified=true') -or !$fileTypes.Contains('explicitBinaryAssociationPreserved=true') -or !$fileTypes.Contains('registeredLanguageAssociationPreserved=true')) { throw 'Source file type fallback policy failed' }
    $expectedVersion = ([xml](Get-Content -LiteralPath (Join-Path $root 'product/resources/idea/AlhenaApplicationInfo.xml') -Raw)).component.version.full
    $platform = Get-Content (Join-Path $root 'upstream.lock.json') -Raw | ConvertFrom-Json
    $version = Get-Content (Join-Path $launch.productRoot 'alhena-version.json') -Raw | ConvertFrom-Json
    if ($version.productVersion -ne $expectedVersion -or $version.platformVersion -ne $platform.applicationVersion -or $version.platformCommit -ne $platform.commit -or $version.runtimeBuild -ne $platform.runtime.build) { throw 'Packaged product/platform version metadata mismatch' }
    if (!$snapshot.Contains('applicationVersion='+$expectedVersion) -or !$snapshot.Contains('applicationBuild=AL-252.')) { throw 'Runtime product/platform identity mismatch' }
    [void](& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-about -Evidence ($relative+'\about'))
    $aboutDeadline=(Get-Date).AddSeconds(20)
    do {
        $about=(& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-inspect -Evidence ($relative+'\about')) -join "`n"
        if ($about.Contains('label=Alhena '+$expectedVersion) -and $about.Contains('Build #AL-252.')) { break }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $aboutDeadline)
    if (!$about.Contains('label=Alhena '+$expectedVersion) -or !$about.Contains('Build #AL-252.')) { throw 'Original About dialog does not show independent product version and platform build' }
    [void](& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage ui-click -Payload Close -Evidence ($relative+'\about-close'))
    Check-Log
    $hash=$launch.archiveSha256
    Stop-Test; $launch=$null
    $launch=(& (Join-Path $root 'run.ps1') @archiveArgument -Hidden -FirstLaunch -SandboxDirectory (Join-Path $evidence 'native-welcome')) | ConvertFrom-Json
    $launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'welcome-launch.json') -Encoding utf8
    $jdk=(Get-ChildItem (Join-Path $root '.cache\bootstrap') -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
    $classes=Join-Path $evidence 'classes'
    New-Item -ItemType Directory -Path $classes -Force | Out-Null
    & (Join-Path $jdk javac.exe) -encoding UTF-8 --add-modules jdk.attach -d $classes (Join-Path $PSScriptRoot 'smoke\Attach.java') (Join-Path $PSScriptRoot 'smoke\UiProbe.java')
    if($LASTEXITCODE) { throw '欢迎页探针编译失败' }
    Set-Content (Join-Path $evidence 'MANIFEST.MF') 'Agent-Class: UiProbe' -Encoding ascii
    $agent=Join-Path $evidence 'welcome-probe.jar'
    & (Join-Path $jdk jar.exe) cfm $agent (Join-Path $evidence 'MANIFEST.MF') -C $classes .
    if($LASTEXITCODE) { throw '欢迎页探针打包失败' }
    $deadline=(Get-Date).AddSeconds(25)
    do {
        & (Join-Path $jdk java.exe) --add-modules jdk.attach -cp $classes Attach $launch.pid $agent ($evidence+'|inspect')
        if($LASTEXITCODE) { throw '欢迎页探针失败' }
        $welcome=Get-Content (Join-Path $evidence 'inspect.txt') -Raw
        if($welcome.Contains('Open Repository') -and $welcome.Contains('Clone Repository')) { break }
        Start-Sleep -Milliseconds 400
    } while((Get-Date) -lt $deadline)
    if(!$welcome.Contains('Open Repository') -or !$welcome.Contains('Clone Repository') -or $welcome.Contains('New Project')) { throw '独立欢迎页入口不符合预期' }
    Check-Log
    $result=[ordered]@{ status='passed'; archiveSha256=$hash; evidence=$evidence; checks=@('native first launch with missing config directory','original Git history shown automatically','independent product version in original About dialog','packaged version metadata matches pinned platform and runtime','staging enabled by default','source text fallback preserves existing language, binary and filename associations','original Git actions in product toolbar','IDE Run/Build/Code/Refactor menu entries removed','unrelated tool windows unavailable','IDE/plugin updates disabled','independent no-telemetry provider','welcome Open Repository and Clone Repository entries','no SEVERE/ERROR log entries') }
    $result | ConvertTo-Json | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json
} finally { Stop-Test }
