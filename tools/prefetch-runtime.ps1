param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$lock = Get-Content -LiteralPath (Join-Path $projectRoot 'upstream.lock.json') -Raw | ConvertFrom-Json
$runtime = $lock.runtime
if ($runtime.sha256 -notmatch '^[a-f0-9]{64}$' -or [IO.Path]::GetFileName($runtime.cacheFile) -ne $runtime.cacheFile) { throw 'Invalid runtime lock entry' }
$sourceRoot = Join-Path $projectRoot $lock.checkout
$cacheFile = [IO.Path]::GetFullPath((Join-Path $sourceRoot ("build\download\" + $runtime.cacheFile)))
if (!$cacheFile.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime cache outside workspace' }
function Test-RuntimeArchive([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -ne $runtime.size) { return $false }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $runtime.sha256
}
if (Test-RuntimeArchive $cacheFile) { Write-Output 'Lightweight JBR cache verified'; return }
if ($Offline) { throw '离线 JBR 归档缺失或 SHA-256 不符；不会尝试联网下载。' }
$downloads = Join-Path $projectRoot 'out\downloads'
New-Item -ItemType Directory -Path $downloads -Force | Out-Null
$archive = Join-Path $downloads ($runtime.url.Split('/')[-1])
if (!(Test-RuntimeArchive $archive)) {
    Write-Output "Downloading pinned lightweight JBR: $($runtime.url)"
    & curl.exe --fail --location --connect-timeout 20 --max-time 300 --retry 2 --silent --show-error --output $archive $runtime.url
    if ($LASTEXITCODE -ne 0) { throw "JBR download failed: $LASTEXITCODE" }
}
if (!(Test-RuntimeArchive $archive)) { throw 'JBR size or SHA-256 does not match upstream.lock.json' }
New-Item -ItemType Directory -Path (Split-Path $cacheFile -Parent) -Force | Out-Null
Copy-Item -LiteralPath $archive -Destination $cacheFile
Write-Output "Pinned lightweight JBR cached: $cacheFile"
