<#
    Invoke-Step: the only sanctioned way to run long work in a chain.

    Dot-source it, then every step goes through it:

        . "$PSScriptRoot\steps.ps1"

        Invoke-Step -Name 'C faces' `
            -Preflight     { ... prove it works on a handful; $true / $false } `
            -Start         { ... launch and RETURN the process(es) } `
            -Progress      { ... a number that must go UP while it works } `
            -Postcondition { ... prove it actually did the thing; $true / $false } `
            -ExpectedUnits 51797

    WHY IT EXISTS

    On 2026-09-12 three separate pieces of work ran confidently and did the wrong
    thing. None crashed. None overspent. Every guard the project had was aimed at
    crashes and money:

      build_inventory   33 minutes, 12,988 videos, wrote no duration at all,
                        because ffprobe was looked for under the wrong username
                        and a missing binary returned an empty dict.
      step B            was about to re-judge 19,684 files sixty times - about
                        $530 - because a re-judge's "outstanding" count is a
                        constant, not a countdown.
      step A            took 3h19m against a 20-minute estimate, because the
                        real number of rotated images was 19,878 and not ~5,000.
                        Nothing said so until it finished.

    The first needed a PREFLIGHT. The second needed a LOOP INVARIANT. The third
    needed a CHECKPOINT that recalibrates out loud. This runner makes all three
    automatic and mandatory, so that they apply to work nobody has written yet.

    WHAT CANNOT BE BYPASSED, HONESTLY

    A parameter that is missing is not a step that runs unguarded - it is an
    exception. All four scriptblocks are Mandatory, so a step cannot be added
    without them; passing { $true } is possible but it is a visible, reviewable
    lie in the diff rather than an omission nobody notices.

    Anyone can still run python by hand outside a chain. What is enforced is that
    nothing enters a CHAIN ungated, and tests/test_chain_gating.py fails the
    build if a chain script launches a subprocess outside Invoke-Step. That is
    the real boundary and it is worth stating plainly rather than claiming the
    guard is absolute.
#>

# NO Set-StrictMode here. This file is dot-sourced, so a strict mode set at the
# top would land in the CALLING chain's scope and change how every line of it
# behaves - including chains written before the rule existed, mid-run, at night.
# A safety helper must not alter the semantics of the thing it is helping.

function Invoke-Step {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]      $Name,

        # Prove the mechanism works on a tiny sample BEFORE committing hours to
        # it. Must return $true. This is the guard build_inventory needed: it is
        # cheaper to find a missing binary in five seconds than in 33 minutes.
        [Parameter(Mandatory = $true)][scriptblock] $Preflight,

        # Launch the real work and RETURN the process or processes. The runner
        # owns the waiting so it can checkpoint while they run - a step that
        # blocks internally cannot be supervised.
        [Parameter(Mandatory = $true)][scriptblock] $Start,

        # A number that must increase while the work runs: rows written, files
        # done, bytes produced. The runner uses it to detect a step that is alive
        # but achieving nothing, and to recalibrate the estimate out loud.
        [Parameter(Mandatory = $true)][scriptblock] $Progress,

        # Prove the work actually happened. A step that exits 0 having written
        # nothing must not be allowed to look like success.
        [Parameter(Mandatory = $true)][scriptblock] $Postcondition,

        # Prove the work is CORRECT, repeatedly, while it runs.
        #
        # This is the one the first version of this file was missing, and the
        # omission cost five hours. -Progress answers "is it moving?" and the
        # answer was yes, beautifully, for five hours, while every face embedding
        # written was attached to the wrong photograph. A row count climbing is
        # not evidence of anything except a row count climbing.
        #
        # A -Verify block must RE-DERIVE a sample of the output from its source
        # and compare, rather than inspect the output's shape. Every cheap shape
        # check passed on that corrupt file: well-formed rows, valid unit
        # vectors, plausible counts. Validity is not correctness, and only
        # recomputing the answer could tell them apart.
        #
        # It runs after the first checkpoint and every -VerifyEvery checkpoints
        # after that, so corruption surfaces in the first hour rather than at the
        # end - or, as happened, never, until somebody thought to ask.
        [Parameter(Mandatory = $true)][scriptblock] $Verify,

        # What the step thinks it is worth. Divergence is reported, not enforced:
        # being wrong about scale is normal, not knowing you were is the problem.
        [double] $ExpectedUnits = 0,

        # A double, not an int, purely so the test suite can drive a checkpoint
        # every few seconds. A supervisor that has never been watched supervising
        # is exactly the kind of unproven machinery this file exists to forbid.
        [double] $CheckpointMin = 10,
        [int]    $StallStrikes  = 3,
        # Run -Verify every Nth checkpoint. 1 = every one. The default of 4 puts
        # a correctness check roughly hourly at the standard 15-minute cadence,
        # which caps the damage of a silent corruption at about an hour of work.
        [int]    $VerifyEvery   = 4
    )

    if (-not (Get-Command Say -ErrorAction SilentlyContinue)) {
        throw "Invoke-Step needs a Say function from the calling chain"
    }
    if (-not (Get-Command Stop-Chain -ErrorAction SilentlyContinue)) {
        throw "Invoke-Step needs a Stop-Chain function from the calling chain"
    }

    # ---- 1. preflight --------------------------------------------------------
    Say "[$Name] preflight"
    $ok = $false
    try { $ok = [bool](& $Preflight) }
    catch { Stop-Chain "[$Name] preflight threw: $_" }
    if (-not $ok) { Stop-Chain "[$Name] preflight failed - not committing to the full run" }
    Say "[$Name] preflight OK"

    # ---- 2. start, and take a baseline before anything runs ------------------
    $p0 = 0.0
    try { $p0 = [double](& $Progress) } catch { $p0 = 0.0 }
    $t0 = Get-Date
    Say ("[$Name] starting (progress baseline {0:N0}{1})" -f $p0,
         $(if ($ExpectedUnits -gt 0) { ", expecting ~{0:N0} units" -f $ExpectedUnits } else { "" }))

    $procs = @(& $Start) | Where-Object { $_ -is [System.Diagnostics.Process] }
    if (-not $procs) { Stop-Chain "[$Name] -Start returned no process to supervise" }

    # ---- 3. supervise: checkpoint, recalibrate, and refuse to run on nothing --
    $last = $p0
    $strikes = 0
    $ticks = 0
    $nextCheck = (Get-Date).AddMinutes($CheckpointMin)
    while ($procs | Where-Object { -not $_.HasExited }) {
        Start-Sleep -Seconds 15
        if ((Get-Date) -lt $nextCheck) { continue }
        $nextCheck = (Get-Date).AddMinutes($CheckpointMin)
        $ticks++

        # CORRECTNESS, not just motion. Runs on the first checkpoint so a broken
        # step is caught in minutes rather than at the end, and periodically
        # after that so a corruption that starts mid-run is caught mid-run.
        if ($ticks -eq 1 -or ($ticks % $VerifyEvery) -eq 0) {
            $good = $false
            try { $good = [bool](& $Verify) }
            catch { Stop-Chain "[$Name] verify threw at checkpoint ${ticks}: $_" }
            if (-not $good) {
                foreach ($p in $procs) { if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
                Stop-Chain "[$Name] VERIFY FAILED at checkpoint $ticks - the output is being written INCORRECTLY. Stopped rather than produce more of it."
            }
            Say "[$Name] verify OK (checkpoint $ticks)"
        }

        $now = $last
        try { $now = [double](& $Progress) } catch { }
        $mins = ((Get-Date) - $t0).TotalMinutes
        $done = $now - $p0
        $rate = if ($mins -gt 0) { $done / $mins } else { 0 }

        if ($now -le $last) {
            $strikes++
            Say ("[$Name] CHECKPOINT: no progress in {0} min (strike {1}/{2}), still at {3:N0}" -f `
                 $CheckpointMin, $strikes, $StallStrikes, $now)
            if ($strikes -ge $StallStrikes) {
                foreach ($p in $procs) { if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
                Stop-Chain ("[$Name] stalled: {0} consecutive checkpoints with no progress over {1} minutes. Alive is not the same as working." -f $strikes, ($strikes * $CheckpointMin))
            }
        } else {
            $strikes = 0
            $msg = "[$Name] CHECKPOINT: {0:N0} done in {1:N0} min ({2:N1}/min)" -f $done, $mins, $rate
            # RECALIBRATION. Step A ran for three hours against a twenty-minute
            # estimate and said nothing. An estimate that is wrong is fine; an
            # estimate that is wrong in silence is what wastes a night.
            if ($ExpectedUnits -gt 0 -and $rate -gt 0) {
                $etaMin = [math]::Max(0, ($ExpectedUnits - $done) / $rate)
                $msg += ", ETA {0:N0} min" -f $etaMin
                if ($done -gt $ExpectedUnits * 1.5) {
                    $msg += " -- RECALIBRATE: already {0:N0} against an expected {1:N0}" -f $done, $ExpectedUnits
                }
            }
            Say $msg
            $last = $now
        }
    }

    # ---- 4. verify once more at the end, then the postcondition --------------
    # The last stretch of work has never been verified by a checkpoint, because
    # the process exited before the next one was due.
    $codes = ($procs | ForEach-Object { $_.ExitCode }) -join ','
    $good = $false
    try { $good = [bool](& $Verify) }
    catch { Stop-Chain "[$Name] final verify threw: $_" }
    if (-not $good) {
        Stop-Chain "[$Name] FINAL VERIFY FAILED (exit codes: $codes) - the step finished, and what it produced is wrong."
    }
    Say "[$Name] final verify OK"

    $ok = $false
    try { $ok = [bool](& $Postcondition) }
    catch { Stop-Chain "[$Name] postcondition threw: $_" }
    if (-not $ok) {
        Stop-Chain "[$Name] postcondition FAILED (exit codes: $codes). The step finished without doing what it claims to do."
    }

    $final = $last
    try { $final = [double](& $Progress) } catch { }
    Say ("[$Name] done in {0:N0} min, progress {1:N0} -> {2:N0}, exit {3}" -f `
         ((Get-Date) - $t0).TotalMinutes, $p0, $final, $codes)
    return $true
}
