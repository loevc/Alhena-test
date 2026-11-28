param([Parameter(Mandatory=$true)][string]$Context, [Parameter(Mandatory=$true)][string]$CloneResult, [string]$Archive, [switch]$CancelAuthentication)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$cacheRoot = [IO.Path]::GetFullPath((Join-Path $root '.cache\remote-test')) + '\'
$contextFile = [IO.Path]::GetFullPath($Context)
if (!$contextFile.StartsWith($cacheRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Context outside remote test cache' }
$remote = Get-Content -LiteralPath $contextFile -Raw | ConvertFrom-Json
$clone = Get-Content -LiteralPath $CloneResult -Raw | ConvertFrom-Json
if ($remote.repository -ne 'loevc/Alhena-test' -or $remote.status -ne 'ready' -or $clone.status -ne 'passed') { throw 'Inactive or unauthorized fixture' }
$repo = [IO.Path]::GetFullPath($clone.fixture)
$fixtureRoot = [IO.Path]::GetFullPath((Join-Path $root 'out\fixtures')) + '\'
if (!$repo.StartsWith($fixtureRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Not a fixture repository' }
$url = if ($clone.transport -eq 'ssh') { $remote.sshUrl } else { $remote.httpsUrl }
if ($CancelAuthentication -and $clone.transport -ne 'https') { throw 'Authentication cancellation mode requires HTTPS' }
function Git([string]$Directory, [string[]]$Arguments) {
    $output = & git.exe -c "safe.directory=$Directory" -C $Directory @Arguments
    if ($LASTEXITCODE) { throw "Fixture Git failed: $($Arguments[0])" }
    return ($output -join "`n").Trim()
}
if ((Git $repo @('remote','get-url','origin')) -ne $url) { throw 'Wrong clone origin' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$branch = 'alhena-ui-' + $stamp + '-' + $clone.transport
$testFile = 'ui-remote-' + $stamp + '.txt'
$incomingFile = 'incoming-remote-' + $stamp + '.txt'
$relative = 'out\remote-sync\' + $stamp + '-' + $clone.transport
$evidence = Join-Path $root $relative
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$checks = [Collections.Generic.List[string]]::new()
$helperObserved = $false
$previousSsh = $env:GIT_SSH_COMMAND
$launch = $null
function Probe([string]$Stage, [string]$Payload = '', [string]$Step = $Stage) {
    (& (Join-Path $PSScriptRoot 'workflow-probe.ps1') -Stage $Stage -Payload $Payload -Evidence ($relative+'\'+$Step)) -join "`n"
}
function Wait-Until([scriptblock]$Condition, [string]$Name) {
    $deadline = (Get-Date).AddSeconds(90)
    do {
        if (& $Condition) { $checks.Add($Name); Write-Output "PASS $Name"; return }
        Start-Sleep -Milliseconds 600
    } while ((Get-Date) -lt $deadline)
    throw "Timed out: $Name; see $evidence"
}
try {
    if ($clone.transport -eq 'ssh') {
        foreach ($keyPath in @($remote.privateKeyPath,$remote.knownHostsPath)) {
            if (![IO.Path]::GetFullPath($keyPath).StartsWith($cacheRoot,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $keyPath)) { throw 'Invalid SSH fixture file' }
        }
        $env:GIT_SSH_COMMAND = 'ssh -i "' + $remote.privateKeyPath.Replace('\','/') + '" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="' + $remote.knownHostsPath.Replace('\','/') + '" -o BatchMode=yes'
    }
    [void](Git $repo @('config','user.name','Alhena Remote Fixture'))
    [void](Git $repo @('config','user.email','fixture@example.invalid'))
    Add-Content -LiteralPath (Join-Path $repo '.git\info\exclude') -Value "`n.idea/`n*.iml" -Encoding ascii
    [void](Git $repo @('checkout','-b',$branch))
    [void](Git $repo @('push','-u','origin',$branch))
    $initialHead = Git $repo @('rev-parse','HEAD')
    [IO.File]::WriteAllText((Join-Path $repo $testFile), "Commit and push through Alhena $($clone.transport).`n")
    & (Join-Path $PSScriptRoot 'compile-workflow-probe.ps1')
    $launchArguments = @{Repository=$repo;Smoke=$true;Hidden=$true}
    if ($Archive) { $launchArguments.Archive=$Archive }
    $launch = (& (Join-Path $root 'run.ps1') @launchArguments) | ConvertFrom-Json
    if ($launch.archiveSha256 -ne $clone.archiveSha256) { throw 'ZIP changed since clone acceptance' }
    $launch | ConvertTo-Json | Set-Content (Join-Path $evidence 'launch.json') -Encoding utf8
    Wait-Until {
        $log = Join-Path $launch.sandbox 'log\idea.log'
        (Test-Path $log) -and ((Get-Content $log -Raw) -match 'Git version for ')
    } 'native Git ready'
    [void](Probe ui-stage-open)
    Wait-Until { (Probe ui-inspect '' 'stage') -match [regex]::Escape($testFile) } 'new file appears in original staging UI'
    [void](Probe ui-stage-all)
    Wait-Until { (Git $repo @('diff','--cached','--name-only')) -eq $testFile } 'original Stage All writes index'
    Wait-Until { (Probe ui-inspect '' 'staged') -match ('(?m)^node=\[, Staged, .*'+[regex]::Escape($testFile)+'\]') } 'staging UI refreshes before commit'
    $message = 'Alhena real ' + $clone.transport + ' UI push ' + $stamp
    [void](Probe ui-message $message 'commit')
    [void](Probe ui-commit '' 'commit')
    Wait-Until { (Git $repo @('log','-1','--format=%s')) -eq $message } 'original Commit creates test commit'
    $head = Git $repo @('rev-parse','HEAD')
    [void](Probe ui-push-open '' 'push')
    Wait-Until { (Probe ui-inspect '' 'push') -match 'button=Push enabled=true' } 'original Push preview'
    [void](Probe ui-push '' 'push')
    if ($CancelAuthentication) {
        Wait-Until { (Probe ui-inspect '' 'auth-cancel') -match 'title=Log In to' } 'original authentication dialog appears'
        [void](Probe ui-auth-cancel '' 'auth-cancel')
        Wait-Until { (Probe ui-inspect '' 'auth-cancel-return') -notmatch 'title=Log In to' } 'authentication cancellation returns control'
        if (!(Git $repo @('ls-remote','origin',('refs/heads/'+$branch))).StartsWith($initialHead)) { throw 'Cancelled authentication changed remote branch' }
        if ((Git $repo @('rev-parse','HEAD')) -ne $head -or (Git $repo @('status','--porcelain'))) { throw 'Cancelled authentication lost local commit' }
        [void](Probe ui-push-open '' 'retry-push')
        Wait-Until { (Probe ui-inspect '' 'retry-push') -match 'button=Push enabled=true' } 'Push can be reopened after authentication cancellation'
        $result = [ordered]@{status='passed';archiveSha256=$launch.archiveSha256;repository=$url;transport=$clone.transport;scenario='cancel HTTPS Push authentication';branch=$branch;fixture=$repo;evidence=$evidence;localHead=$head;remoteHead=$initialHead;checks=$checks.ToArray()}
        $result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
        $result | ConvertTo-Json -Depth 5
        return
    }
    Wait-Until {
        $snapshot = Probe ui-inspect '' 'auth'
        if ($snapshot -match 'title=Log In to GitHub|title=Log In to github.com|button=.*[Cc]redential helper') {
            [void](Probe ui-auth-helper '' 'auth-helper')
            $script:helperObserved = $true
        }
        (Git $repo @('ls-remote','origin',('refs/heads/'+$branch))).StartsWith($head)
    } 'original Push updates real GitHub branch'
    $peer = Join-Path $fixtureRoot ('workflow-peer-'+$stamp+'-'+$clone.transport)
    & git.exe clone --single-branch --branch $branch $url $peer
    if ($LASTEXITCODE) { throw 'Peer clone failed' }
    [IO.File]::WriteAllText((Join-Path $peer $incomingFile), "Incoming from acceptance peer.`n")
    [void](Git $peer @('add',$incomingFile))
    [void](Git $peer @('-c','user.name=Alhena Peer','-c','user.email=fixture@example.invalid','commit','-m','Incoming real remote update'))
    [void](Git $peer @('push','origin',$branch))
    $peerHead = Git $peer @('rev-parse','HEAD')
    [void](Probe ui-fetch)
    Wait-Until { (Git $repo @('rev-parse',('origin/'+$branch))) -eq $peerHead } 'original Fetch updates tracking ref'
    [void](Probe ui-update-open '' 'pull')
    Wait-Until { (Probe ui-inspect '' 'pull') -match 'title=Update Project' } 'original Update dialog'
    [void](Probe ui-update '' 'pull')
    Wait-Until { (Git $repo @('rev-parse','HEAD')) -eq $peerHead } 'original Update integrates real remote commit'
    if ((Git $repo @('status','--porcelain')) -or !(Test-Path (Join-Path $repo $incomingFile))) { throw 'Unexpected final worktree' }
    $log = Get-Content (Join-Path $launch.sandbox 'log\idea.log') -Raw
    if ($log -match '\] (?:SEVERE|\s*ERROR) - ') { throw 'Severe application log errors' }
    $result = [ordered]@{status='passed';archiveSha256=$launch.archiveSha256;repository=$url;transport=$clone.transport;branch=$branch;fixture=$repo;evidence=$evidence;credentialHelperDialogObserved=$helperObserved;pushedHead=$head;pulledHead=$peerHead;checks=$checks.ToArray()}
    $result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 5
} finally {
    $env:GIT_SSH_COMMAND = $previousSsh
    if ($launch) {
        $candidate = Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
        if ($candidate -and $candidate.Path -eq (Join-Path $launch.productRoot 'bin\alhena64.exe')) { Stop-Process -Id $launch.pid }
    }
}
