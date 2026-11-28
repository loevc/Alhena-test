param(
    [ValidateSet('Prepare','Audit','Compile','Package')][string]$Action = 'Audit',
    [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$lock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'upstream.lock.json') -Raw | ConvertFrom-Json
$sourceRoot = Join-Path $PSScriptRoot $lock.checkout

if ($Offline) {
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw '离线包仅支持 Windows x64 构建主机。' }
    $statePath = Join-Path $PSScriptRoot '.cache\offline-state.json'
    if (!(Test-Path -LiteralPath $statePath) -or !(Test-Path -LiteralPath (Join-Path $sourceRoot '.git'))) {
        throw '请先用 tools/offline-kit.py restore 恢复已校验的离线包；离线模式不会克隆或下载源码。'
    }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state.upstreamCommit -ne $lock.commit) { throw '离线包的上游版本与当前源码锁文件不一致。' }
}

if (!(Test-Path -LiteralPath (Join-Path $sourceRoot '.git'))) {
    & git -c core.longpaths=true -c core.autocrlf=input clone --depth 1 --branch $lock.tag $lock.repository $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw '下载上游源码失败' }
}
& python (Join-Path $PSScriptRoot 'tools\workspace.py') prepare
if ($LASTEXITCODE -ne 0) { throw '准备产品覆盖文件失败' }
if ($Action -eq 'Prepare') { return }
& python (Join-Path $PSScriptRoot 'tools\workspace.py') audit
if ($LASTEXITCODE -ne 0) { throw '依赖检查未通过' }
if ($Action -eq 'Audit') { return }
if ($Action -eq 'Package') { & (Join-Path $PSScriptRoot 'tools\prefetch-runtime.ps1') -Offline:$Offline }

$bootstrap = Join-Path $sourceRoot 'platform\jps-bootstrap\jps-bootstrap.cmd'
if (!(Test-Path -LiteralPath $bootstrap)) { throw '缺少 JPS bootstrap；请先补齐上游工作树。' }
$buildAction = if ($Action -eq 'Package') { 'package' } else { 'compile' }
$arguments = @('-Dintellij.build.target.os=windows', '-Dintellij.build.target.arch=x64', '-Didea.dev.build.unpacked=true', "-Dalhena.build.action=$buildAction", $sourceRoot, $lock.buildModule, $lock.buildTarget)
$previousLocalAppData = $env:LOCALAPPDATA
$savedBuildEnvironment = @{}
foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'BOOTSTRAP_SYSTEM_PROPERTIES', 'JPS_BOOTSTRAP_CLASSES_FROM_JPS_BUILD', 'JPS_BOOTSTRAP_MANIFEST_JSON_URL', 'JPS_BOOTSTRAP_WORKDIR', 'TEAMCITY_VERSION')) {
    $savedBuildEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
# Upstream bootstrap downloads and replaces a versioned JBR directory below this
# location. Keep that target within this workspace, rather than a shared IDE cache.
$bootstrapCache = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.cache\bootstrap'))
if (!$bootstrapCache.StartsWith($PSScriptRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw '缓存路径超出工作区' }
New-Item -ItemType Directory -Path (Join-Path $bootstrapCache 'Temp\JetBrains') -Force | Out-Null
$logDirectory = Join-Path $PSScriptRoot 'out\logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logFile = Join-Path $logDirectory ("{0}-{1}.log" -f $buildAction, (Get-Date -Format 'yyyyMMdd-HHmmss'))
Push-Location $sourceRoot
try {
    $env:LOCALAPPDATA = $bootstrapCache
    if ($Offline) {
        # user.home is consumed directly by both Ant and JPS; maven.repo.local
        # alone does not redirect all of this pinned upstream's dependency code.
        $offlineHome = Join-Path $PSScriptRoot '.cache\offline-home'
        if (!(Test-Path -LiteralPath (Join-Path $offlineHome '.m2\repository'))) { throw '离线 Maven 仓库不存在。' }
        $bootstrapJavac = @(Get-ChildItem -LiteralPath $bootstrapCache -Filter javac.exe -Recurse)
        if ($bootstrapJavac.Count -ne 1) { throw '离线 bootstrap JDK 缺失或存在多个候选。' }
        $jdkBin = Split-Path $bootstrapJavac[0].FullName -Parent
        $guardDirectory = Join-Path $PSScriptRoot '.cache\offline-guard'
        $guardClasses = Join-Path $guardDirectory 'classes'
        New-Item -ItemType Directory -Path $guardClasses -Force | Out-Null
        foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'BOOTSTRAP_SYSTEM_PROPERTIES', 'JPS_BOOTSTRAP_MANIFEST_JSON_URL', 'JPS_BOOTSTRAP_WORKDIR', 'TEAMCITY_VERSION')) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        }
        & (Join-Path $jdkBin 'javac.exe') --release 17 -d $guardClasses (Join-Path $PSScriptRoot 'tools\offline\NoNetwork.java')
        if ($LASTEXITCODE -ne 0) { throw '离线网络防护编译失败。' }
        $guardJar = Join-Path $guardDirectory 'no-network.jar'
        & (Join-Path $jdkBin 'jar.exe') --create --file $guardJar -C $guardClasses .
        if ($LASTEXITCODE -ne 0) { throw '离线网络防护打包失败。' }
        # Inherited by Ant, JPS and Java compiler/build children. External Java
        # connections fail instead of silently falling back to an online mirror.
        # Settings traversal constructs the Plugins page even without a frame;
        # its metadata refresh ignores normal update preferences. Use upstream's
        # repository-host override only in build JVMs, leaving app resources intact.
        $env:JAVA_TOOL_OPTIONS = '"-Duser.home={0}" "-Xbootclasspath/a:{1}" -Djava.security.manager=alhena.offline.NoNetwork -Didea.plugins.host=http://127.0.0.1:9' -f $offlineHome, $guardJar
        $env:JPS_BOOTSTRAP_CLASSES_FROM_JPS_BUILD = 'true'
    }
    Write-Output "构建日志：$logFile"
    # Windows PowerShell 5.1 turns redirected native stderr into ErrorRecords.
    # Keep diagnostics in the UTF-8 log and decide success by the native exit code.
    $savedErrorPreference = $ErrorActionPreference
    $logWriter = New-Object IO.StreamWriter($logFile, $false, (New-Object Text.UTF8Encoding($false)))
    try {
        $ErrorActionPreference = 'Continue'
        & $bootstrap @arguments 2>&1 | ForEach-Object -ErrorAction Stop {
            $message = $_.ToString()
            $logWriter.WriteLine($message)
            Write-Output $message
        }
        $bootstrapExitCode = $LASTEXITCODE
    } finally {
        $logWriter.Dispose()
        $ErrorActionPreference = $savedErrorPreference
    }
    if ($bootstrapExitCode -ne 0) { throw "上游构建失败，退出码：$bootstrapExitCode" }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    foreach ($name in $savedBuildEnvironment.Keys) {
        if ($null -eq $savedBuildEnvironment[$name]) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($name, $savedBuildEnvironment[$name], 'Process') }
    }
    Pop-Location
}
