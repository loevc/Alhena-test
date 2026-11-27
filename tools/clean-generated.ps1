param([switch]$Apply, [ValidateRange(2,100)][int]$KeepNewest = 2)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$outputRoot = Join-Path $root 'out'
$candidates = [Collections.Generic.List[object]]::new()

function Assert-PlainDirectory([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (!$full.StartsWith($outputRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup target outside project out directory' }
    $cursor = $full
    while ($cursor.Length -ge $outputRoot.Length) {
        $item = Get-Item -LiteralPath $cursor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Cleanup refuses reparse point: $cursor" }
        $cursor = Split-Path $cursor -Parent
    }
    return $full
}
function Measure-PlainTree([string]$Path) {
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($Path)
    [long]$bytes = 0
    while ($pending.Count) {
        foreach ($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Cleanup refuses nested reparse point: $($entry.FullName)" }
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) } else { $bytes += $entry.Length }
        }
    }
    return $bytes
}
# These contain disposable IDE indexes from isolated acceptance runs. Logs,
# screenshots, results, fixture repositories, releases and build caches stay.
foreach ($category in @('welcome-smoke','remote-sync','workflow-smoke','product-smoke','smoke')) {
    $directory = Join-Path $outputRoot $category
    if (!(Test-Path -LiteralPath $directory -PathType Container)) { continue }
    [void](Assert-PlainDirectory $directory)
    $runs = @(Get-ChildItem -LiteralPath $directory -Directory | Where-Object { $_.Name -match '^\d{8}-\d{6}(?:-(?:https|ssh))?$' } | Sort-Object Name -Descending)
    foreach ($run in $runs | Select-Object -Skip $KeepNewest) {
        [void](Assert-PlainDirectory $run.FullName)
        # Only known sandbox locations are eligible, never arbitrary recursion.
        foreach ($sandbox in @('', 'native-sandbox','cli-sandbox','native-project','native-welcome')) {
            $base = if ($sandbox) { Join-Path $run.FullName $sandbox } else { $run.FullName }
            $system = Join-Path $base 'system'
            if (!(Test-Path -LiteralPath $system -PathType Container)) { continue }
            [void](Assert-PlainDirectory $system)
            foreach ($cacheName in @('caches','index','tmp','vcs-log')) {
                $cachePath = Join-Path $system $cacheName
                if (!(Test-Path -LiteralPath $cachePath -PathType Container)) { continue }
                $full = Assert-PlainDirectory $cachePath
                $candidates.Add([pscustomobject][ordered]@{path=$full;bytes=(Measure-PlainTree $full);reason='old isolated acceptance index cache'})
            }
        }
    }
}
$plan = [ordered]@{schemaVersion=1;mode=$(if($Apply){'apply'}else{'dry-run'});keepNewest=$KeepNewest;targets=$candidates.ToArray();totalBytes=($candidates | Measure-Object -Property bytes -Sum).Sum;preserved=@('all source and Git repositories','release ZIPs and extracted applications','compilation and dependency caches','acceptance logs, screenshots and reports')}
$plan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputRoot 'cleanup-generated-plan.json') -Encoding utf8
if ($Apply) {
    if (Get-Process -Name alhena64 -ErrorAction SilentlyContinue) { throw 'Close Alhena before deleting acceptance caches; plan saved, nothing deleted' }
    foreach ($candidate in $candidates) {
        $full = Assert-PlainDirectory $candidate.path
        [void](Measure-PlainTree $full)
        Remove-Item -LiteralPath $full -Recurse -Force
    }
    $plan.completed = $true
    $plan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputRoot 'cleanup-generated-result.json') -Encoding utf8
}
$plan | ConvertTo-Json -Depth 5
