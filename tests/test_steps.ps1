<#
    Prove Invoke-Step supervises before it is trusted to supervise.

        pwsh -NoProfile -File tests\test_steps.ps1

    It is about to be put in charge of a fourteen-hour unattended run. The whole
    point of the thing is that unproven machinery must not be committed to, and
    a supervisor nobody has watched supervising is unproven machinery.

    Four behaviours, each one a real failure from 2026-09-12:

      1. a failing preflight stops before the work         (ffprobe: 33 wasted minutes)
      2. a healthy step runs and reports                   (the happy path still works)
      3. a step that finishes without doing anything stops (0.0% Duration, exit code 0)
      4. a step that is alive but achieving nothing stops  (a loop that repeats rather than retries)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\guards\steps.ps1"

$script:FAILURES = @()
$script:HALT = $null

# The chain supplies these two; the test supplies fakes so a Stop-Chain can be
# caught rather than exiting the test runner.
function Say($m) { Write-Host "      | $m" }
function Stop-Chain([string] $why) { $script:HALT = $why; throw "STOP-CHAIN: $why" }

function Check($name, $got, $want) {
    $ok = $got -eq $want
    "  {0,-56} {1}" -f $name, $(if ($ok) { 'OK' } else { "FAIL got=$got want=$want" }) | Write-Host
    if (-not $ok) { $script:FAILURES += $name }
}

# a short-lived real process to supervise
function Start-Sleeper([double] $sec) {
    Start-Process pwsh -PassThru -WindowStyle Hidden `
        -ArgumentList @('-NoProfile', '-Command', "Start-Sleep -Seconds $sec")
}

Write-Host ''
Write-Host '1. a failing preflight must stop before any work starts'
$script:HALT = $null
$started = $false
try {
    Invoke-Step -Name 'test-preflight' `
        -Preflight { $false } `
        -Start { $script:started = $true; Start-Sleeper 1 } `
        -Progress { 1 } -Postcondition { $true } -Verify { $true }
} catch { }
Check 'halted' ($null -ne $script:HALT) $true
Check 'the work never started' $started $false

Write-Host ''
Write-Host '2. a healthy step runs to completion'
$script:HALT = $null
$script:counter = 0
$done = $false
try {
    $done = Invoke-Step -Name 'test-happy' `
        -Preflight { $true } `
        -Start { Start-Sleeper 4 } `
        -Progress { $script:counter += 10; $script:counter } `
        -Postcondition { $true } -Verify { $true } `
        -CheckpointMin 0.02 -ExpectedUnits 100
} catch { }
Check 'returned true' $done $true
Check 'did not halt' ($null -eq $script:HALT) $true

Write-Host ''
Write-Host '3. a step that exits cleanly having done nothing must stop'
$script:HALT = $null
try {
    Invoke-Step -Name 'test-postcondition' `
        -Preflight { $true } `
        -Start { Start-Sleeper 2 } `
        -Progress { 5 } `
        -Postcondition { $false } -Verify { $true } `
        -CheckpointMin 5
} catch { }
Check 'halted on the postcondition' ($script:HALT -like '*postcondition FAILED*') $true

Write-Host ''
Write-Host '4. a step that is alive but making no progress must stop'
$script:HALT = $null
$t0 = Get-Date
try {
    Invoke-Step -Name 'test-stall' `
        -Preflight { $true } `
        -Start { Start-Sleeper 120 } `
        -Progress { 7 } `
        -Postcondition { $true } -Verify { $true } `
        -CheckpointMin 0.02 -StallStrikes 2
} catch { }
$elapsed = ((Get-Date) - $t0).TotalSeconds
Check 'halted on the stall' ($script:HALT -like '*stalled*') $true
Check 'killed it rather than waiting out the 120s' ($elapsed -lt 60) $true

Write-Host ''
Write-Host '5. output being written INCORRECTLY must stop the run, not finish it'
$script:HALT = $null
$script:n = 0
$t0 = Get-Date
try {
    Invoke-Step -Name 'test-verify' `
        -Preflight { $true } `
        -Start { Start-Sleeper 120 } `
        -Progress { $script:n += 5; $script:n } `
        -Postcondition { $true } `
        -Verify { $false } `
        -CheckpointMin 0.02 -VerifyEvery 1
} catch { }
$el = ((Get-Date) - $t0).TotalSeconds
Check 'halted on the verify' ($script:HALT -like '*VERIFY FAILED*') $true
Check 'killed the work rather than letting it continue' ($el -lt 60) $true

Write-Host ''
Write-Host '7. a gate that LOGS before answering must still be able to say no'
# The 2026-09-18 failure, exactly. chain_mirror_h.ps1 logged with
# `... | Tee-Object -FilePath $log -Append`, which writes the line to the OUTPUT
# stream as well as the file. So a Postcondition that said two things and then
# returned $false emitted @('...', '...', $false), and [bool] of a non-empty
# array is $true. The chain exited 0 with 172.5 GB unsent, the scheduled task
# went Ready instead of restarting, and - worse - the -Verify gate in that chain
# had never been able to fail at all.
#
# These fakes emit to the output stream on purpose. A runner that cannot be
# lied to by a chatty gate is the thing being tested, not the two chains that
# were fixed.
$script:HALT = $null
try {
    Invoke-Step -Name 'test-chatty-postcondition' `
        -Preflight { $true } `
        -Start { Start-Sleeper 2 } `
        -Progress { 5 } `
        -Postcondition { 'files still to send: 52'; 'failing on purpose'; $false } `
        -Verify { $true } `
        -CheckpointMin 5
} catch { }
Check 'a chatty postcondition still halts' ($script:HALT -like '*postcondition FAILED*') $true

$script:HALT = $null
$started = $false
try {
    Invoke-Step -Name 'test-chatty-preflight' `
        -Preflight { 'the one-file probe FAILED'; $false } `
        -Start { $script:started = $true; Start-Sleeper 1 } `
        -Progress { 1 } -Postcondition { $true } -Verify { $true }
} catch { }
Check 'a chatty preflight still halts' ($script:HALT -like '*preflight failed*') $true
Check 'and the work never started' $started $false

$script:HALT = $null
$script:m = 0
try {
    Invoke-Step -Name 'test-chatty-verify' `
        -Preflight { $true } `
        -Start { Start-Sleeper 60 } `
        -Progress { $script:m += 5; $script:m } `
        -Postcondition { $true } `
        -Verify { 're-derived 4 sampled row(s), 3 wrong'; $false } `
        -CheckpointMin 0.02 -VerifyEvery 1
} catch { }
Check 'a chatty verify still halts' ($script:HALT -like '*VERIFY FAILED*') $true

$script:HALT = $null
try {
    Invoke-Step -Name 'test-silent-gate' `
        -Preflight { $true } `
        -Start { Start-Sleeper 2 } `
        -Progress { 5 } `
        -Postcondition { } `
        -Verify { $true } `
        -CheckpointMin 5
} catch { }
Check 'a gate that answers NOTHING is a no, not a yes' ($script:HALT -like '*postcondition FAILED*') $true

Write-Host ''
Write-Host '6. a step cannot be added without its guards'
$missing = $false
try {
    Invoke-Step -Name 'test-missing' -Preflight { $true } -Start { Start-Sleeper 1 } -Progress { 1 } -Postcondition { $true }
} catch { $missing = $true }
Check 'omitting -Verify is an error' $missing $true

Write-Host ''
if ($script:FAILURES.Count) {
    Write-Host ("{0} FAILED: {1}" -f $script:FAILURES.Count, ($script:FAILURES -join ', '))
    exit 1
}
Write-Host 'all checks passed'
exit 0
