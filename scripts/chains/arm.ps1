<#
    Run a chain so that it OUTLIVES the session that started it.

        pwsh -NoProfile -File scripts\chains\arm.ps1 -Chain chain_phase3_resume.ps1
        pwsh -NoProfile -File scripts\chains\arm.ps1 -Status
        pwsh -NoProfile -File scripts\chains\arm.ps1 -Stop

    WHY NOT Start-Process -WindowStyle Hidden

    Because it does not detach. On 2026-09-12 the classifier, and both chains
    waiting on it, were launched that way and all three died in the same second
    the agent session ended - 26,000 files short, after four hours of paid work.
    Hidden only hides a window. The process stays in the caller's tree and dies
    with it.

    A scheduled task is owned by the Task Scheduler service instead, so it
    survives the session ending, the terminal closing, and logging out. It does
    not survive a reboot by design: -Stop, or a reboot, are the two ways this
    stops, and both are deliberate.

    Detachment alone turned out not to be enough: a properly detached chain was
    still killed two hours in on 2026-09-12, so the task is also registered with
    RestartCount and every chain is written to resume. Everything in
    scripts/chains is safe to re-run, so a death costs only the work in flight.

    -Status is worth trusting over intuition. `schtasks /query` prints "Ready"
    for a task that is not currently running, which reads like "fine"; the state
    that means running is "Running".
#>
[CmdletBinding()]
param(
    [string] $Chain,
    [string] $TaskName = 'contentarchives-chain',
    [switch] $Status,
    [switch] $Stop
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Stopping the TASK kills its pwsh, but the python it launched keeps running as
# an orphan - and an orphaned classifier goes on spending money against the same
# todo list the next run will claim, so the same file is paid for twice. Seen for
# real on 2026-09-12: a re-arm left pid 29248 classifying with a dead parent while
# its replacement started up. Unregistering a task is not stopping the work.
function Stop-ChainWorkers {
    $ours = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'classify_live|faces_embed|refix_rotated|master_sheet|build_inventory' }
    foreach ($w in $ours) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($w.ParentProcessId)" -ErrorAction SilentlyContinue
        if (-not $parent) {
            $what = @("classify_live","faces_embed","refix_rotated","master_sheet","build_inventory") | Where-Object { $w.CommandLine -match $_ } | Select-Object -First 1
            Write-Host ("  orphan {0} ({1}) - stopping" -f $w.ProcessId, $what)
            Stop-Process -Id $w.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Show-Status {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Host "no task '$TaskName' registered"; return }
    $i = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host ("task    : {0}" -f $t.TaskName)
    Write-Host ("state   : {0}" -f $t.State)
    Write-Host ("started : {0}" -f $i.LastRunTime)
    Write-Host ("result  : {0}" -f $i.LastTaskResult)
    Write-Host ("action  : {0} {1}" -f $t.Actions[0].Execute, $t.Actions[0].Arguments)
}

if ($Status) { Show-Status; exit 0 }

if ($Stop) {
    Stop-ScheduledTask    -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Stop-ChainWorkers
    Write-Host "stopped and unregistered '$TaskName'"
    Write-Host "NOTE: python children are not killed by this. Check with:"
    Write-Host "  Get-CimInstance Win32_Process -Filter \"Name='python.exe'\""
    exit 0
}

if (-not $Chain) { throw "give -Chain <file in scripts\chains>, or -Status / -Stop" }

$script = Join-Path $PSScriptRoot $Chain
if (-not (Test-Path $script)) { throw "no such chain: $script" }

# A task left over from a previous arming would otherwise refuse the register -
# and its python workers would outlive it, so reap them before starting new ones.
Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Start-Sleep -Seconds 2
}
# Unconditionally, NOT only when a task existed: a previous arming that failed
# part-way leaves no task but live workers, and that is precisely when an orphan
# is waiting to be found.
Stop-ChainWorkers

$pwshExe = (Get-Process -Id $PID).Path
$action  = New-ScheduledTaskAction -Execute $pwshExe `
             -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $script) `
             -WorkingDirectory $repo

# ExecutionTimeLimit 0 = no limit. The default is three days, which would kill a
# long classification mid-run and look like a crash.
#
# RestartCount is the outer half of the recovery. On 2026-09-12 a chain that WAS
# properly detached (parent svchost, verified) was still killed two hours in with
# LastTaskResult 0xC000013A - no reboot, empty System log, settings correct.
# Something outside Windows kills long jobs on this machine under memory
# pressure. Rather than keep hunting it, the Task Scheduler service restarts the
# task when it exits non-zero, and every chain is written to resume, so a kill
# costs about a minute instead of hours. A chain that fails for a real reason
# still stops: it says STOPPED and exits 1 after its own bounded retries.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -StartWhenAvailable `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
              -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1)

# -LogonType Interactive: the chain reads GOOGLE_API_KEY from HKCU\Environment
# and writes to mapped drives, both of which need the real user's profile.
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
               -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Settings $settings `
    -Principal $principal -Description "contentarchives: $Chain" | Out-Null
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 5
Write-Host "armed $Chain as scheduled task '$TaskName'"
Show-Status
