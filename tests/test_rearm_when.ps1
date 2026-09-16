<#
    Prove rearm_when.ps1 fires when it should, and only then.

        pwsh -NoProfile -File tests\test_rearm_when.ps1

    It was armed on 2026-09-12 without ever being watched doing its job, and it
    failed at both ends:

      * it wrote "watching for 'step B done'" INTO the log it was grepping for
        "step B done", matched itself, and re-armed the live chain instantly -
        killing a running step B at 3,000 of 19,684 and skipping it entirely.
      * once that was fixed it still died at the real moment, exit 1 with no
        error anywhere, because it appended arm.ps1's output to the chain's own
        log - the file the chain was writing at that exact second, since the
        thing it fires on is something the chain just wrote.

    Both are the same mistake in different clothes: a watcher entangled with the
    thing it watches. Hence the three checks below.

    arm.ps1 is replaced by a stub, so the test never touches a real task.
#>

$ErrorActionPreference = 'Stop'
$FAILURES = @()

function Check($name, $got, $want) {
    $ok = $got -eq $want
    "  {0,-56} {1}" -f $name, $(if ($ok) { 'OK' } else { "FAIL got=$got want=$want" }) | Write-Host
    if (-not $ok) { $script:FAILURES += $name }
}

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("rearm-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $sandbox | Out-Null
try {
    Copy-Item "$PSScriptRoot\..\guards\rearm_when.ps1" $sandbox
    # a stub in place of the real launcher, so nothing real is re-armed
    @'
param([string]$Chain, [string]$ChainArgs, [switch]$Status, [switch]$Stop)
Write-Host "STUB-ARM chain=$Chain args=$ChainArgs"
'@ | Set-Content (Join-Path $sandbox 'arm.ps1')

    $watched = Join-Path $sandbox 'watched.log'
    $notes   = Join-Path $sandbox 'notes.log'
    # the marker is ALREADY in history, from a previous run of the chain
    Set-Content -Path $watched -Value '01:00:00  step B done   (an earlier run)'

    # Every value that contains a space MUST be quoted here. Start-Process joins
    # -ArgumentList with plain spaces, so `-ChainArgs -From C` arrives as three
    # tokens and the binder never sees "-From C" - the watcher then dies on
    # parameter binding before writing a single line, which looks exactly like
    # the bug being tested for.
    $p = Start-Process pwsh -PassThru -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f (Join-Path $sandbox 'rearm_when.ps1')),
        '-Marker', '"step B done"', '-ChainArgs', '"-From C"',
        '-Log', ('"{0}"' -f $watched), '-NoteLog', ('"{0}"' -f $notes),
        '-TimeoutMin', '2')

    Write-Host ''
    Write-Host '1. it must NOT fire on the marker already in history, nor on its own notes'
    Start-Sleep -Seconds 25
    Check 'still watching after 25s' (-not $p.HasExited) $true
    $n = if (Test-Path $notes) { Get-Content $notes -Raw } else { '' }
    Check 'has not re-armed' ($n -notmatch 'STUB-ARM') $true
    Check 'its notes are not in the watched log' `
        ((Get-Content $watched -Raw) -notmatch 'rearm_when') $true

    Write-Host ''
    Write-Host '2. it must fire when the marker is appended AFTER it started'
    Add-Content -Path $watched -Value '02:03:15  step B done'
    $deadline = (Get-Date).AddSeconds(60)
    while (-not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    Check 'exited after firing' $p.HasExited $true
    $n = Get-Content $notes -Raw
    Check 'called the launcher' ($n -match 'STUB-ARM') $true
    Check 'passed the chain args through' ($n -match 'args=-From C') $true

    Write-Host ''
    Write-Host '3. the launcher output must land in the notes, not the watched log'
    Check 'arm output captured in notes' ($n -match 'arm: STUB-ARM') $true
    Check 'watched log never written to' `
        ((Get-Content $watched -Raw) -notmatch 'STUB-ARM') $true
}
finally {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
if ($FAILURES.Count) {
    Write-Host ("{0} FAILED: {1}" -f $FAILURES.Count, ($FAILURES -join ', '))
    exit 1
}
Write-Host 'all checks passed'
exit 0
