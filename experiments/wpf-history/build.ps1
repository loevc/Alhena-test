param([switch]$Test, [switch]$Run)
$ErrorActionPreference = 'Stop'
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$compiler = Join-Path $framework 'csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw '需要 Windows .NET Framework 4.x。' }
$output = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$references = @('System.dll','System.Core.dll','System.Xaml.dll','System.Windows.Forms.dll','WPF\WindowsBase.dll','WPF\PresentationCore.dll','WPF\PresentationFramework.dll') | ForEach-Object { '/reference:' + (Join-Path $framework $_) }
$sources = Get-ChildItem (Join-Path $PSScriptRoot 'src') -Filter '*.cs' | ForEach-Object FullName
& $compiler /nologo /target:winexe /platform:anycpu /codepage:65001 /out:"$output\Alhena.exe" @references @sources
if ($LASTEXITCODE -ne 0) { throw '编译失败' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'src\Alhena.exe.config') -Destination $output
if ($Test) {
    & $compiler /nologo /target:exe /codepage:65001 /out:"$output\Alhena.Tests.exe" /main:Alhena.Tests /reference:System.dll /reference:System.Core.dll (Join-Path $PSScriptRoot 'src\Git.cs') (Join-Path $PSScriptRoot 'src\Graph.cs') (Join-Path $PSScriptRoot 'tests\Tests.cs')
    if ($LASTEXITCODE -ne 0) { throw '测试编译失败' }
    & "$output\Alhena.Tests.exe"
    if ($LASTEXITCODE -ne 0) { throw '测试失败' }
    & $compiler /nologo /target:exe /codepage:65001 /out:"$output\Alhena.UiTests.exe" /reference:"$output\Alhena.exe" @references (Join-Path $PSScriptRoot 'tests\UiTests.cs')
    if ($LASTEXITCODE -ne 0) { throw '界面测试编译失败' }
    & "$output\Alhena.UiTests.exe"
    if ($LASTEXITCODE -ne 0) { throw '界面测试失败' }
}
if ($Run) { Start-Process -FilePath "$output\Alhena.exe" }
