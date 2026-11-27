param([string]$Repository, [switch]$Smoke, [switch]$Hidden, [string]$Archive, [string]$SandboxDirectory, [switch]$FirstLaunch)
$ErrorActionPreference = 'Stop'
$sourceRoot = Join-Path $PSScriptRoot 'upstream\intellij-community'
$archiveFile = if ($Archive) { Get-Item -LiteralPath $Archive } else {
    foreach ($candidateDirectory in @((Join-Path $sourceRoot 'out\alhena\artifacts'), (Join-Path $PSScriptRoot 'out\releases'))) {
        if (Test-Path -LiteralPath $candidateDirectory) {
            $candidate = Get-ChildItem -LiteralPath $candidateDirectory -Filter 'alhena-*.win.zip' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($candidate) { $candidate; break }
        }
    }
}
if (!$archiveFile) { throw '未找到程序包。请使用 -Archive 指定 ZIP，或执行 .\build.ps1 -Action Package。' }
if ($archiveFile.PSIsContainer -or $archiveFile.Extension -ne '.zip') { throw '-Archive 必须指定 ZIP 文件。' }
$hash = (Get-FileHash -LiteralPath $archiveFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$runDirectory = Join-Path $PSScriptRoot ("out\run\" + $hash.Substring(0,12))
$marker = Join-Path $runDirectory '.extracted'
if (!(Test-Path -LiteralPath $marker)) {
    if (Test-Path -LiteralPath $runDirectory) { $runDirectory += '-' + [Guid]::NewGuid().ToString('N').Substring(0,8); $marker = Join-Path $runDirectory '.extracted' }
    Expand-Archive -LiteralPath $archiveFile.FullName -DestinationPath $runDirectory
    Set-Content -LiteralPath $marker -Value $hash -Encoding ascii
}
$launcher = Get-ChildItem -LiteralPath $runDirectory -Filter alhena64.exe -Recurse | Where-Object { $_.Directory.Name -eq 'bin' } | Select-Object -First 1
if (!$launcher) { throw '发行包中未找到 bin\alhena64.exe' }
$productRoot = Split-Path $launcher.Directory.FullName -Parent
if ($Repository) {
    $Repository = (Resolve-Path -LiteralPath $Repository).Path
    if (!(Test-Path -LiteralPath $Repository -PathType Container)) { throw '仓库路径必须是目录' }
}
if ($Smoke) {
    $fixtureRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'out\fixtures')) + [IO.Path]::DirectorySeparatorChar
    if (!$Repository -or !$Repository.StartsWith($fixtureRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Smoke 仅允许 out\fixtures 下的测试仓库' }
}
$sandboxRelative = if ($Smoke) { 'out\smoke\' + (Get-Date -Format 'yyyyMMdd-HHmmss') } else { 'out\sandbox' }
$sandbox = Join-Path $PSScriptRoot $sandboxRelative
if ($SandboxDirectory) {
    $sandbox = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($SandboxDirectory)) { $SandboxDirectory } else { Join-Path $PSScriptRoot $SandboxDirectory }))
    $outputRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'out')) + [IO.Path]::DirectorySeparatorChar
    if (!$sandbox.StartsWith($outputRoot,[StringComparison]::OrdinalIgnoreCase)) { throw '独立运行目录必须在工作区 out 内' }
}
if ($FirstLaunch -and !$SandboxDirectory) { throw '首次启动检查必须显式指定独立目录' }
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
# IntelliJ checks whether config exists before acquiring its directory lock.
# Pre-create our own empty directories so first launch never imports IDE settings.
foreach ($name in @('config','system','log','plugins')) {
    if ($FirstLaunch -and $name -eq 'config') { continue }
    New-Item -ItemType Directory -Path (Join-Path $sandbox $name) -Force | Out-Null
}
$properties = Join-Path $sandbox 'alhena.properties'
$settings = @(
    ('idea.config.path=' + (Join-Path $sandbox 'config').Replace('\','/'))
    ('idea.system.path=' + (Join-Path $sandbox 'system').Replace('\','/'))
    ('idea.log.path=' + (Join-Path $sandbox 'log').Replace('\','/'))
    ('idea.plugins.path=' + (Join-Path $sandbox 'plugins').Replace('\','/'))
    'idea.initially.ask.config=false'
    'idea.disable.collect.statistics=true'
    'idea.suppress.statistics.report=true'
)
if ($Smoke) { $settings += 'idea.trust.all.projects=true' }
[IO.File]::WriteAllLines($properties, $settings, (New-Object Text.UTF8Encoding($false)))
$previousProperties = $env:ALHENA_PROPERTIES
try {
    $env:ALHENA_PROPERTIES = $properties
    $launchOptions = @{ FilePath = $launcher.FullName; WorkingDirectory = $productRoot; PassThru = $true }
    if ($Hidden) { $launchOptions.WindowStyle = 'Hidden' }
    if ($Repository) { $launchOptions.ArgumentList = '"' + [regex]::Replace($Repository, '(\\+)$', '$1$1') + '"' }
    $requested = Get-Date
    $process = Start-Process @launchOptions
} finally { $env:ALHENA_PROPERTIES = $previousProperties }
$result = [ordered]@{ pid = $process.Id; productRoot = $productRoot; sandbox = $sandbox; repository = $Repository; archiveSha256 = $hash; started = $requested.ToString('o') }
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'out\last-launch.json') -Encoding utf8
$result | ConvertTo-Json
