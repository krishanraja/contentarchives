# Resume phase 3 from wherever the store got to, and run through to the end of
# phase 3b - surviving being killed, because on this machine it will be.
#
# HISTORY, BECAUSE IT EXPLAINS THE SHAPE OF THIS FILE
#
# 2026-09-12 12:56  the classifier died in the same second an agent session
#                   ended, at 53,325/79,017. Launched with `Start-Process pwsh
#                   -WindowStyle Hidden`, which hides a window but leaves the
#                   process in the caller's tree. Learning 38.
# 2026-09-12 15:10  relaunched as a scheduled task - genuinely detached, parent
#                   svchost - and killed anyway at 14,750/25,695, two hours in,
#                   with LastTaskResult 0xC000013A (STATUS_CONTROL_C_EXIT). No
#                   Windows cause: no reboot, empty System log, task settings
#                   correct. Something outside Windows kills long jobs on this
#                   box under memory pressure, as it killed five tracked tasks
#                   the day before.
#
# So this no longer tries to avoid the kill. It makes the kill cost nothing.
#
# Two layers, because either alone has a hole:
#   inner - each classify step loops until the store says nothing is left, so a
#           killed python is retried by the surviving pwsh within a minute.
#   outer - arm.ps1 registers the task with RestartCount, so a killed pwsh is
#           restarted by the Task Scheduler service itself.
#
# Both are safe to repeat. classify_live skips any hash this model has already
# tagged, the store is append-per-file, refix_rotated only rewrites thumbnails
# that are actually wrong, and master_sheet is a pure rebuild. Nothing here can
# pay twice for the same file.
$log  = 'D:\_PhotoAudit\phase3.log'
$repo = 'C:\Users\krish\dev\contentarchives'
function Say($m) { "$((Get-Date).ToString('HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }

$env:PYTHONIOENCODING = 'utf-8'
$e = Get-ItemProperty -Path 'HKCU:\Environment'
$env:GOOGLE_API_KEY = $e.GOOGLE_API_KEY
if (-not $env:GOOGLE_API_KEY) { Say 'STOPPED: GOOGLE_API_KEY not in HKCU\Environment'; exit 1 }

# A HALT file is how a deliberate stop survives a restart. Without it the outer
# RestartCount would drive straight through the spend ceiling - the brake would
# stop the process and the scheduler would start it again, 99 times. A brake a
# restart loop can push through is not a brake.
#
# So: a real failure writes HALT and exits 1 (honest, and the task result shows
# it). The restart that follows sees HALT and exits 0, which ends the cycle. A
# kill writes nothing, so a killed run just resumes, which is the whole point.
$halt = 'D:\_PhotoAudit\PHASE3-HALTED.txt'
function Stop-Chain([string] $why) {
    Say "STOPPED: $why"
    "$((Get-Date).ToString('u'))  $why" | Set-Content -Path $halt -Encoding utf8
    Say "wrote $halt - delete it once the cause is fixed, then re-arm."
    exit 1
}
if (Test-Path $halt) {
    Say "halted by a previous run, not restarting: $(Get-Content $halt -Raw)"
    Say 'delete D:\_PhotoAudit\PHASE3-HALTED.txt once the cause is fixed, then re-arm.'
    exit 0
}


# What is still outstanding, asked of the store rather than assumed. Returns
# @(files, estimated_usd), or @(-1, 0) if the answer could not be read - which
# is treated as a stop, not as zero.
function Get-Outstanding([string[]] $extra) {
    $out = & python "$repo\engine\classify_live.py" --thumbs D:\_thumbs `
             --store D:\_enrichment @extra 2>&1 | Out-String
    $n = [regex]::Match($out, 'to classify:\s*([\d,]+) files')
    $c = [regex]::Match($out, 'estimate\s*:\s*\$([\d.]+)')
    if (-not $n.Success) { return @(-1, 0.0) }
    return @([int]($n.Groups[1].Value -replace ',', ''),
             $(if ($c.Success) { [double]$c.Groups[1].Value } else { 0.0 }))
}

# Run the classifier until the store says there is nothing left. The ceiling is
# recomputed from what actually remains on every attempt, so restarting cannot
# quietly multiply a per-run budget into an unbounded one.
function Invoke-Classify([string] $label, [string[]] $extra) {
    for ($try = 1; $try -le 60; $try++) {
        $o = Get-Outstanding $extra
        $left = [int]$o[0]; $est = [double]$o[1]
        if ($left -lt 0) { Stop-Chain "${label} could not read the outstanding count from classify_live" }
        if ($left -eq 0) { Say "${label}: nothing outstanding"; return $true }

        $ceiling = [math]::Round([math]::Max(2.0, $est * 1.6) , 2)
        Say ("{0}: attempt {1}, {2:N0} files outstanding, est `${3:N2}, ceiling `${4:N2}" -f `
             $label, $try, $left, $est, $ceiling)

        $before = if (Test-Path $log) { (Get-Item $log).Length } else { 0 }
        python -u "$repo\engine\classify_live.py" --thumbs D:\_thumbs --store D:\_enrichment `
               --workers 12 --max-usd $ceiling @extra --apply *>> $log

        # Only this attempt's output counts - an earlier attempt's ceiling line
        # must not stop a later one.
        $fresh = ''
        if (Test-Path $log) {
            $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
            try { $null = $fs.Seek($before, 'Begin'); $fresh = (New-Object IO.StreamReader($fs)).ReadToEnd() }
            finally { $fs.Dispose() }
        }
        if ($fresh -match 'CEILING REACHED') {
            Stop-Chain "${label} hit its spend ceiling. Raise it deliberately, or find out why the measured rate beat the estimate."
        }
    }
    Stop-Chain "${label} still unfinished after 60 attempts - something is failing, not just being killed."
}

Say '=== chain start (resumable; safe to restart at any point) ==='

# --- the rest of phase 3 -----------------------------------------------------
if (-not (Invoke-Classify 'step 3b classify' @())) { exit 1 }
Say 'step 3b done'

# Videos had no Duration, Width or Height at all - 12,988 of them, 0.0%
# populated - because scripts/build_inventory.py hardcoded ffprobe under
# C:\Users\user\ and this machine's user is krish. probe_video() returned an
# empty dict when the binary was missing, so a 33-minute pass reported success
# and wrote nothing. ffprobe is resolved from PATH now, and shouts if absent.
#
# This runs BEFORE the sheet so the rebuild picks the durations up, rather than
# building a sheet that is knowingly missing a column and rebuilding it later.
Say 'step 3a-video: re-probing videos now that ffprobe resolves'
python -u "$repo\scripts\build_inventory.py" --video *>> $log
if ($LASTEXITCODE -ne 0) { Say "WARNING: build_inventory exited $LASTEXITCODE - continuing; it is an independent input to the sheet" }
Say 'step 3a-video done'

Say 'step 3c: rebuilding MASTER.csv and scoring coverage'
python -u "$repo\tools\master_sheet.py" *>> $log
Say 'PHASE 3 COMPLETE. Review the coverage table above, then decide segmentation.'

# --- phase 3b ----------------------------------------------------------------
Say 'step A: regenerating thumbnails for rotated originals'
python -u "$repo\tools\refix_rotated.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain "refix_rotated exited $LASTEXITCODE" }

if (Test-Path D:\_PhotoAudit\ROTATED-REDO.txt) {
    if (-not (Invoke-Classify 'step B re-judge rotated' @('--only-list', 'D:\_PhotoAudit\ROTATED-REDO.txt'))) { exit 1 }
} else {
    Say 'step B: no ROTATED-REDO.txt - nothing to re-judge'
}
Say 'step B done'

# Three shards, not six. Measured on this machine 2026-09-12: one shard does
# 0.85 images/sec and peaks at 630 MB. The CPU is an i5-1135G7 - FOUR physical
# cores - and detection runs on CPUExecutionProvider, so six shards each taking
# an onnxruntime thread pool oversubscribe the cores several times over and add
# contention rather than throughput. Six would also hold ~3.8 GB against ~2.7 GB
# free, and memory pressure is what has been killing long jobs on this box all
# day. Three holds ~1.9 GB and still saturates four cores.
#
# Aggregate throughput is CPU-bound at roughly 1 image/sec whatever the shard
# count, so the 51,797 images with a face in them are an overnight job. Shard
# count is a safety choice here, not a speed one. The lever that WOULD change
# the runtime is --det-size, and it trades away small and distant faces, so it
# is Krish's call rather than a default to quietly change.
#
# Resumability is by content hash in faces.csv, not by shard, so changing the
# shard count never re-does an image that is already embedded.
Say 'step C: faces, three shards (4 cores; six oversubscribes them)'
$jobs = @()
foreach ($i in 0..2) {
    $jobs += Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
        '-u', "$repo\engine\faces_embed.py", '--thumbs', 'D:\_thumbs',
        '--store', 'D:\_enrichment', '--shard', "$i/3"
    ) -RedirectStandardOutput "D:\_PhotoAudit\faces-$i.log" -RedirectStandardError "D:\_PhotoAudit\faces-$i.err"
}
Say ("face shards: " + ($jobs.Id -join ', '))
$jobs | Wait-Process
Say 'faces done'

Say 'step D: rebuilding the sheet'
python -u "$repo\tools\master_sheet.py" *>> $log
Say 'PHASE 3B COMPLETE. Re-run the receipt sweep now the library is fully classified.'
