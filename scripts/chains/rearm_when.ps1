<#
    Wait for a marker to appear in the chain log, then re-arm the chain from a
    later step. Registered as its own scheduled task so it survives everything
    the main chain survives.

        pwsh -File rearm_when.ps1 -Marker 'step B re-judge' -ChainArgs '-From B' -Register

    WHY THIS EXISTS

    On 2026-09-12 a bug was found in step B while step A had been running for
    three hours. The running chain holds its script in memory, so the fix could
    only be loaded by restarting - and `refix_rotated` is NOT incremental, so
    restarting step A would have thrown away three hours and paid for them
    again. The fix could only be loaded safely in the seconds after step A
    finished and before step B's second pass began.

    That moment was unpredictable and possibly at 3am. The whole lesson of this
    project's worst days is that the gap between a job finishing and somebody
    noticing is the biggest source of wasted wall-clock, so the swap is done by
    a watcher rather than by a person staying awake.

    It is deliberately dumb: poll a log for a string, run one command, exit. It
    unregisters itself when it fires, so it cannot fire twice.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Marker,
    [string] $ChainArgs  = '',
    [string] $Chain      = 'chain_phase3_resume.ps1',
    [string] $Log        = 'D:\_PhotoAudit\phase3.log',
    [string] $TaskName   = 'contentarchives-swap',
    [string] $NoteLog    = 'D:\_PhotoAudit\rearm_when.log',
    [int]    $TimeoutMin = 720,
    [switch] $Register,
    [switch] $Stop
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot

# Notes go to their OWN file, never to the log being watched. Writing
# "watching for 'step B done'" into the file you are grepping for "step B done"
# makes the watcher match itself and fire instantly - which it did on
# 2026-09-12, killing a running step B and jumping the chain forward. A watcher
# must not be able to see its own voice.
function Note($m) {
    $line = "$((Get-Date).ToString('HH:mm:ss'))  [rearm_when] $m"
    Add-Content -Path $NoteLog -Value $line
    Write-Host $line
}

if ($Stop) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "unregistered '$TaskName'"
    exit 0
}

if ($Register) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    $pwshExe = (Get-Process -Id $PID).Path
    $arg = ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -Marker "{1}" ' +
            '-ChainArgs "{2}" -Chain "{3}" -TimeoutMin {4}') -f `
           (Join-Path $here 'rearm_when.ps1'), $Marker, $ChainArgs, $Chain, $TimeoutMin
    $action = New-ScheduledTaskAction -Execute $pwshExe -Argument $arg `
                -WorkingDirectory (Split-Path -Parent (Split-Path -Parent $here))
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                  -DontStopIfGoingOnBatteries -StartWhenAvailable `
                  -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
                  -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal `
                   -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
                   -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Settings $settings `
        -Principal $principal -Description "re-arm the chain when: $Marker" | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3
    Write-Host ("armed watcher '{0}': on '{1}' -> arm.ps1 {2}" -f $TaskName, $Marker, $ChainArgs)
    Write-Host ("state: " + (Get-ScheduledTask -TaskName $TaskName).State)
    exit 0
}

# ---- the watch itself -------------------------------------------------------
#
# Only text appended AFTER this point counts. A chain log accumulates across
# runs, so "step B done" from an earlier run is already sitting in it and a
# naive search fires immediately on history rather than on the event. Recording
# the length first turns "does the log contain X" into "has X happened since I
# started watching", which is the actual question.
$startLen = if (Test-Path $Log) { (Get-Item $Log).Length } else { 0 }
Note "watching from byte $startLen (timeout ${TimeoutMin}m)"

function Get-NewText {
    if (-not (Test-Path $Log)) { return '' }
    $fs = [IO.File]::Open($Log, 'Open', 'Read', 'ReadWrite')
    try {
        if ($fs.Length -le $startLen) { return '' }
        $null = $fs.Seek($startLen, 'Begin')
        return (New-Object IO.StreamReader($fs)).ReadToEnd()
    } finally { $fs.Dispose() }
}

$deadline = (Get-Date).AddMinutes($TimeoutMin)
while ((Get-Date) -lt $deadline) {
    if (Test-Path $Log) {
        # Plain substring, not a regex, so a bracket or a dollar in the marker
        # cannot silently change what is being waited for.
        if ((Get-NewText).Contains($Marker)) {
            Note "saw '$Marker' - re-arming with: $ChainArgs"
            & (Join-Path $here 'arm.ps1') -Chain $Chain -ChainArgs $ChainArgs *>> $Log
            Note "re-armed. Unregistering self so this cannot fire twice."
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
            exit 0
        }
    }
    Start-Sleep -Seconds 20
}
Note "TIMED OUT after ${TimeoutMin}m without seeing '$Marker'"
exit 1
