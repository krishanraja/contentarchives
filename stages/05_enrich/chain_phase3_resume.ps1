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
#
# -From skips steps already finished. A chain is a sequence of hours-long jobs,
# and a fix to a LATER step should not cost the earlier ones: on 2026-09-12 a bug
# was found in step B while step A had been running for three hours, and without
# this the only way to load the fix was to throw that away and re-run
# build_inventory and the sheet as well. Re-arm with the step that is about to
# start, having checked the log for what actually completed.
#
#   pwsh -File arm.ps1 -Chain chain_phase3_resume.ps1 -ChainArgs '-From B'
#
param(
    [ValidateSet('3b', '3a-video', '3c', 'A', 'B', 'C', 'D')]
    [string] $From = '3b'
)

$log  = 'D:\_PhotoAudit\phase3.log'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# Write-Host, NOT Tee-Object. Tee passes its string down the pipeline, so a Say
# inside a function becomes part of that function's RETURN VALUE. Should-Run
# returned @('skipping step A', $false), and PowerShell treats a non-empty array
# as true - so every step logged "skipping" and then ran anyway. Caught at 22:41
# on 2026-09-12 with step A about to redo three hours of thumbnails it had just
# finished. A logging helper must be silent on the pipeline.
function Say($m) {
    $line = "$((Get-Date).ToString('HH:mm:ss'))  $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}

$ORDER = @('3b', '3a-video', '3c', 'A', 'B', 'C', 'D')
$FromIx = $ORDER.IndexOf($From)
function Should-Run([string] $step) {
    $i = $ORDER.IndexOf($step)
    if ($i -lt $FromIx) { Say "skipping step $step (already done; resumed from $From)"; return $false }
    return $true
}

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


# Invoke-Step is the only sanctioned way to run work here: it makes a preflight,
# a progress signal and a postcondition mandatory, checkpoints long runs, and
# refuses a step that is alive but achieving nothing.
#
# THE ASSERTION BELOW IS NOT DECORATION. On 2026-09-13 this dot-source was
# missing - an edit that inserted it aborted before writing the file, while the
# Invoke-Step CALLS landed fine. PowerShell's default is to report an unknown
# command and CARRY ON, so the chain skipped every step in silence and printed
# "faces done" and "PHASE 3B COMPLETE" at 02:06 having run no faces at all. A
# guard that is not loaded is indistinguishable from a guard that passes, which
# makes a missing supervisor worse than no supervisor.
. "$PSScriptRoot\steps.ps1"
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load - Invoke-Step is unavailable, so no step could be supervised.'
    exit 1
}

# What is still outstanding, asked of the store rather than assumed. Returns
# @(files, estimated_usd), or @(-1, 0) if the answer could not be read - which
# is treated as a stop, not as zero.
function Get-Outstanding([string[]] $extra) {
    # gate:exempt read-only dry run, seconds, no --apply: this IS a preflight
    $out = & python "$repo\stages\05_enrich\classify_live.py" --thumbs D:\_thumbs `
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
    # --only-list DELIBERATELY ignores what is already done: those files were
    # judged from a sideways thumbnail, so the stored answer is the thing being
    # replaced and skipping them for having one would skip the whole job. That
    # makes "to classify" a CONSTANT for a re-judge, not a countdown - so the
    # outstanding count can never reach zero and cannot be the completion test.
    # Using it as one would have re-run a 19,500-file pass up to 60 times: about
    # $530, a hundred hours, and faces would never have started.
    #
    # For a re-judge, completion is instead "classify_live printed `finished in`
    # in THIS attempt's output", which it does only after draining its queue. A
    # killed pass prints nothing and is retried, which is the behaviour wanted.
    $onlyList = $extra -contains '--only-list'
    $prevLeft = [int]::MaxValue
    for ($try = 1; $try -le 60; $try++) {
        $o = Get-Outstanding $extra
        $left = [int]$o[0]; $est = [double]$o[1]
        if ($left -lt 0) { Stop-Chain "${label} could not read the outstanding count from classify_live" }
        if ($left -eq 0) { Say "${label}: nothing outstanding"; return $true }

        # THE LOOP INVARIANT: a retry must make progress. If a whole attempt ran
        # and the amount of work left did not go DOWN, the loop is not retrying,
        # it is repeating - and repeating a paid pass 60 times is how a $9 step
        # becomes a $530 one. This is the general form of the --only-list bug,
        # and it would have caught it without anyone knowing --only-list existed.
        # Only checked from attempt 2, because attempt 1 has nothing to compare.
        if ($try -gt 1 -and $left -ge $prevLeft -and -not $onlyList) {
            Stop-Chain ("{0}: attempt {1} left {2:N0} outstanding, no better than the {3:N0} before it. A retry that does not reduce the work is repeating it, not resuming it." -f $label, $try, $left, $prevLeft)
        }
        $prevLeft = $left

        $ceiling = [math]::Round([math]::Max(2.0, $est * 1.6) , 2)
        Say ("{0}: attempt {1}, {2:N0} files outstanding, est `${3:N2}, ceiling `${4:N2}" -f `
             $label, $try, $left, $est, $ceiling)

        $before = if (Test-Path $log) { (Get-Item $log).Length } else { 0 }
        $tags = 'D:\_enrichment\content_tags.csv'
        Invoke-Step -Name "$label a$try" -ExpectedUnits $left -CheckpointMin 15 -StallStrikes 3 `
            -Preflight {
                # Cheap, and each one has actually bitten: no key means every
                # call 401s for hours, no thumbnails means paying to label
                # nothing, and an unwritable store means the answers evaporate.
                if (-not $env:GOOGLE_API_KEY) { Say '  no GOOGLE_API_KEY'; return $false }
                if (-not (Test-Path 'D:\_thumbs')) { Say '  no thumbnail cache'; return $false }
                if (-not (Test-Path $tags)) { Say '  no tag store to append to'; return $false }
                return $true
            } `
            -Start {
                Start-Process python -PassThru -WindowStyle Hidden -ArgumentList (@(
                    '-u', "$repo\stages\05_enrich\classify_live.py", '--thumbs', 'D:\_thumbs',
                    '--store', 'D:\_enrichment', '--workers', '12',
                    '--max-usd', $ceiling) + $extra + @('--apply')) `
                    -RedirectStandardOutput 'D:\_PhotoAudit\cls.out' `
                    -RedirectStandardError  'D:\_PhotoAudit\cls.err'
            } `
            -Progress {
                # The store grows a row per answer, so this rises while it works
                # and flatlines the moment it is alive but achieving nothing.
                if (Test-Path $tags) { (Get-Item $tags).Length } else { 0 }
            } `
            -Verify {
                # Re-reads the newest rows the classifier claims to have written
                # and checks they are real answers about real files: a hash that
                # exists in the thumbnail cache, and a `kind` from the vocabulary
                # rather than an empty string or an error message. A pass writing
                # blanks, or writing against hashes nothing else knows, climbs
                # the row count exactly as fast as a good one.
                $chk = & python -c @"
import csv, io, os, sys
rows = list(csv.DictReader(io.open(r'$tags', encoding='utf-8', errors='replace', newline='')))
recent = [r for r in rows[-400:] if r.get('tag') == 'kind']
if len(recent) < 5:
    print('too few new rows to judge'); sys.exit(2)
bad = 0
for r in recent[-25:]:
    h = (r.get('hash') or '').strip()
    v = (r.get('value') or '').strip()
    if not v or len(h) < 16:
        bad += 1; continue
    if not os.path.exists(os.path.join(r'D:\_thumbs', h[:2], h + '.jpg')):
        bad += 1
print('checked {} recent kind rows, {} unusable'.format(min(25, len(recent)), bad))
sys.exit(1 if bad > 2 else 0)
"@ 2>&1 | Out-String
                foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
                return ($LASTEXITCODE -ne 1)
            } `
            -Postcondition {
                Get-Content 'D:\_PhotoAudit\cls.out' -ErrorAction SilentlyContinue | Add-Content -Path $log
                Get-Content 'D:\_PhotoAudit\cls.err' -ErrorAction SilentlyContinue | Add-Content -Path $log
                # A pass may legitimately end by finishing OR by hitting the
                # ceiling; both are handled below. What must not happen is
                # ending having written nothing at all.
                $o = Get-Content 'D:\_PhotoAudit\cls.out' -Raw -ErrorAction SilentlyContinue
                if ($o -match 'finished in|CEILING REACHED') { return $true }
                Say '  classify_live ended without finishing or hitting its ceiling'
                return $false
            }

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
        if ($onlyList -and $fresh -match 'finished in') {
            Say "${label}: pass completed - re-judge does not count down, so one clean pass is the finish line"
            return $true
        }
    }
    Stop-Chain "${label} still unfinished after 60 attempts - something is failing, not just being killed."
}

Say '=== chain start (resumable; safe to restart at any point) ==='

# --- the rest of phase 3 -----------------------------------------------------
if (Should-Run '3b') {
    if (-not (Invoke-Classify 'step 3b classify' @())) { exit 1 }
    Say 'step 3b done'
}

# Videos had no Duration, Width or Height at all - 12,988 of them, 0.0%
# populated - because scripts/build_inventory.py hardcoded ffprobe under
# C:\Users\user\ and this machine's user is krish. probe_video() returned an
# empty dict when the binary was missing, so a 33-minute pass reported success
# and wrote nothing. ffprobe is resolved from PATH now, and shouts if absent.
#
# This runs BEFORE the sheet so the rebuild picks the durations up, rather than
# building a sheet that is knowingly missing a column and rebuilding it later.
if (Should-Run '3a-video') {
    Invoke-Step -Name '3a-video' -ExpectedUnits 82000 -CheckpointMin 10 `
        -Preflight {
            # THE failure this step actually had: ffprobe was looked for under
            # another machine's username, probe_video returned {} in silence, and
            # 33 minutes produced 0.0% duration across 12,988 videos. Five
            # seconds of asking where ffprobe is would have caught all of it.
            $out = & python -c "import importlib.util,sys;spec=importlib.util.spec_from_file_location('bi',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);print(m.FFPROBE or 'NONE')" "$repo\stages\04_inventory\build_inventory.py" 2>&1 | Select-Object -Last 1
            if (-not $out -or "$out" -eq 'NONE' -or -not (Test-Path "$out")) {
                Say "  ffprobe not resolvable ('$out') - every video would silently get no duration"
                return $false
            }
            Say "  ffprobe: $out"
            return $true
        } `
        -Start {
            Start-Process python -PassThru -WindowStyle Hidden `
                -ArgumentList @('-u', "$repo\stages\04_inventory\build_inventory.py", '--video') `
                -RedirectStandardOutput 'D:\_PhotoAudit\inv.out' `
                -RedirectStandardError  'D:\_PhotoAudit\inv.err'
        } `
        -Progress {
            if (Test-Path 'D:\_PhotoAudit\INVENTORY.csv') { (Get-Item 'D:\_PhotoAudit\INVENTORY.csv').Length } else { 0 }
        } `
        -Verify {
            # Re-probes videos the pass has already written and compares the
            # duration on disk with the duration in the file. This is precisely
            # the failure that ran 33 minutes writing nothing: the shape of
            # INVENTORY.csv was perfect throughout.
            $chk = & python "$repo	oolserify_inventory.py" --sample 4 2>&1 | Out-String
            foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            return ($LASTEXITCODE -ne 1)
        } `
        -Postcondition {
            Get-Content 'D:\_PhotoAudit\inv.out' -ErrorAction SilentlyContinue | Add-Content -Path $log
            if (-not (Test-Path 'D:\_PhotoAudit\INVENTORY.csv')) { Say '  no INVENTORY.csv'; return $false }
            # The column this step exists for. 0.0% must never again read as success.
            $rows = Import-Csv 'D:\_PhotoAudit\INVENTORY.csv'
            $vids = @($rows | Where-Object { $_.Kind -eq 'video' })
            $withDur = @($vids | Where-Object { $_.Duration }).Count
            $pct = if ($vids.Count) { 100.0 * $withDur / $vids.Count } else { 0 }
            Say ("  videos {0:N0}, with duration {1:N0} ({2:N1}%)" -f $vids.Count, $withDur, $pct)
            return ($vids.Count -eq 0 -or $pct -ge 50)
        }
    Say 'step 3a-video done'
}

if (Should-Run '3c') {
    Invoke-Step -Name '3c sheet' -CheckpointMin 10 `
        -Preflight {
            foreach ($f in @('D:\_PhotoAudit\INVENTORY.csv', 'D:\_enrichment\content_tags.csv')) {
                if (-not (Test-Path $f)) { Say "  missing join input: $f"; return $false }
                if ((Get-Item $f).Length -lt 1024) { Say "  suspiciously small: $f"; return $false }
            }
            return $true
        } `
        -Start {
            Start-Process python -PassThru -WindowStyle Hidden `
                -ArgumentList @('-u', "$repo\stages\08_index\master_sheet.py") `
                -RedirectStandardOutput 'D:\_PhotoAudit\sheet.out' `
                -RedirectStandardError  'D:\_PhotoAudit\sheet.err'
        } `
        -Progress {
            $t = 'D:\_PhotoAudit\MASTER.csv.tmp'
            if (Test-Path $t) { (Get-Item $t).Length }
            elseif (Test-Path 'D:\_PhotoAudit\MASTER.csv') { (Get-Item 'D:\_PhotoAudit\MASTER.csv').Length }
            else { 0 }
        } `
        -Verify {
            # A sheet is a join, and a broken join produces a complete file with
            # an empty column - which is how OriginPath sat at 0% and Duration at
            # 0.0% while every row looked fine. So: read the newest MASTER.csv
            # and insist the join-dependent columns are actually populated.
            $chk = & python -c @"
import csv, io, sys
p = r'D:\_PhotoAudit\MASTER.csv'
rows = []
with io.open(p, encoding='utf-8', errors='replace', newline='') as f:
    for i, r in enumerate(csv.DictReader(f)):
        rows.append(r)
        if i > 4000: break
if len(rows) < 100:
    print('sheet too small to judge'); sys.exit(2)
def pct(col):
    return 100.0 * sum(1 for r in rows if (r.get(col) or '').strip()) / len(rows)
bad = []
for col, floor in (('Hash', 90), ('Side', 90), ('kind', 50), ('Bytes', 90)):
    v = pct(col)
    print('  {:<8} {:.1f}%'.format(col, v))
    if v < floor: bad.append(col)
if bad: print('join-dependent columns empty: ' + ','.join(bad))
sys.exit(1 if bad else 0)
"@ 2>&1 | Out-String
            foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            return ($LASTEXITCODE -ne 1)
        } `
        -Postcondition {
            Get-Content 'D:\_PhotoAudit\sheet.out' -ErrorAction SilentlyContinue | Add-Content -Path $log
            if (-not (Test-Path 'D:\_PhotoAudit\MASTER.csv')) { Say '  no MASTER.csv'; return $false }
            $age = ((Get-Date) - (Get-Item 'D:\_PhotoAudit\MASTER.csv').LastWriteTime).TotalMinutes
            if ($age -gt 240) { Say "  MASTER.csv is $([int]$age) min old - it was not rewritten"; return $false }
            return $true
        }
    Say 'PHASE 3 COMPLETE. Review the coverage table above, then decide segmentation.'
}

# --- phase 3b ----------------------------------------------------------------
if (Should-Run 'A') {
    # ExpectedUnits is 19,878 because that is what it MEASURED, against an
    # estimate of ~5,000. It ran 3h19m against a 20-minute guess and said nothing
    # for three hours. The checkpoint now recalibrates out loud instead.
    Invoke-Step -Name 'A rotate' -ExpectedUnits 19878 -CheckpointMin 15 `
        -Preflight {
            if (-not (Test-Path 'D:\_thumbs')) { Say '  no thumbnail cache to repair'; return $false }
            # Prove the orientation reader works at all before walking 69,000
            # files: a reader that always returns "upright" would find nothing
            # and report success, which is indistinguishable from a tidy library.
            $ok = & python -c "import importlib.util,sys;spec=importlib.util.spec_from_file_location('rf',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);print('OK' if callable(getattr(m,'orientation',None)) else 'NO')" "$repo\stages\05_enrich\refix_rotated.py" 2>&1 | Select-Object -Last 1
            if ("$ok" -ne 'OK') { Say "  orientation reader unavailable ('$ok')"; return $false }
            return $true
        } `
        -Start {
            Start-Process python -PassThru -WindowStyle Hidden `
                -ArgumentList @('-u', "$repo\stages\05_enrich\refix_rotated.py", '--apply') `
                -RedirectStandardOutput 'D:\_PhotoAudit\refix.out' `
                -RedirectStandardError  'D:\_PhotoAudit\refix.err'
        } `
        -Progress {
            # counts "N regenerated" lines, so it rises while it works
            if (Test-Path 'D:\_PhotoAudit\refix.out') { (Get-Item 'D:\_PhotoAudit\refix.out').Length } else { 0 }
        } `
        -Verify {
            # Counting regenerations proves it REWROTE thumbnails, not that it
            # turned them the right way up. A run that rewrote all 19,870 and
            # left every one sideways prints identical numbers. So compare the
            # original's EXIF orientation with the thumbnail's actual shape.
            $chk = & python "$repo\stages\05_enrich\verify_rotation.py" --sample 6 2>&1 | Out-String
            foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            return ($LASTEXITCODE -ne 1)
        } `
        -Postcondition {
            Get-Content 'D:\_PhotoAudit\refix.out' -ErrorAction SilentlyContinue | Add-Content -Path $log
            if (-not (Test-Path 'D:\_PhotoAudit\ROTATED-REDO.txt')) {
                Say '  no ROTATED-REDO.txt - step B would silently have nothing to do'
                return $false
            }
            return $true
        }
}

if (Should-Run 'B') {
    if (Test-Path D:\_PhotoAudit\ROTATED-REDO.txt) {
        if (-not (Invoke-Classify 'step B re-judge rotated' @('--only-list', 'D:\_PhotoAudit\ROTATED-REDO.txt'))) { exit 1 }
    } else {
        Say 'step B: no ROTATED-REDO.txt - nothing to re-judge'
    }
    Say 'step B done'
}

# ONE shard. Not three, and certainly not six. Measured on this machine at 02:30
# on 2026-09-13, same library, same thumbnails, 150-second samples after letting
# the model load:
#
#     1 shard   107 face rows/min      <- fastest by half again
#     2 shards   70 face rows/min
#     3 shards   70 face rows/min
#
# Parallelism actively HURTS here, which is the opposite of the assumption the
# six-shard original was built on. onnxruntime already spreads one session
# across all four physical cores of this i5-1135G7, so a second process does not
# find idle cores to use - it takes threads and cache from the first, and adds
# ~450 MB on a box that has been killing jobs at ~1 GB free all day.
#
# The three-shard run was on track for about 30 hours. One shard is about 20.
# That difference was invisible until a checkpoint measured the real rate and
# reported it, which is the entire argument for checkpoints.
#
# The remaining lever is --det-size, which trades away small and distant faces -
# in a family library that means people in group shots and backgrounds. That is
# Krish's call, not a default to quietly change, so it stays at 512.
#
# Resumability is by content hash in faces.csv, not by shard, so changing the
# shard count never re-does an image that is already embedded.
if (Should-Run 'C') {
    # PREFLIGHT. Faces is a fourteen-hour step, and the most expensive mistake
    # available is not a crash - it is fourteen hours of work that produces
    # nothing and reports success, which is exactly what build_inventory did for
    # 33 minutes today when ffprobe could not be found.
    #
    # So: prove the pipeline end to end on fifteen images, by checking that
    # faces.csv actually GREW, before committing the night to it. Fifteen images
    # is about a minute, and the rows are real work the full run then skips.
    # The shard arithmetic is worth proving too - the shard count changed from
    # 6 to 3 today, and a shard that silently selects nothing would look
    # identical to a shard that finished.
    # A SHARDED run writes faces.<i>.csv, NOT faces.csv - faces_embed renames the
    # output per shard. The first version of this preflight checked faces.csv,
    # found 0 lines, and halted a pipeline that had just successfully detected 9
    # faces in 8 images. A safeguard that checks the wrong artefact is as
    # dangerous as no safeguard: it blocks good work, or waves bad work through,
    # and in both cases it is trusted. So this counts every faces*.csv.
    function Count-FaceRows {
        $files = Get-ChildItem 'D:\_enrichment\faces*.csv' -ErrorAction SilentlyContinue
        if (-not $files) { return 0 }
        return ($files | ForEach-Object {
            (Get-Content $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        } | Measure-Object -Sum).Sum
    }
    # ExpectedUnits must be in the SAME UNIT as -Progress, and -Progress counts
    # face ROWS, not images. Set to 51,797 (images) it produced an ETA of 720
    # minutes for work that was really ~131,000 rows away - the recalibration
    # said half the truth, confidently. Measured on this library: 2.75 faces per
    # image across 47,721 images with a face in them.
    Invoke-Step -Name 'C faces' -ExpectedUnits 131000 -CheckpointMin 15 -StallStrikes 3 `
        -Preflight {
            # Fourteen hours is the most expensive thing in this pipeline, so the
            # mechanism is proved on fifteen images first. Two conditions, because
            # --limit is applied BEFORE the already-done filter: if those fifteen
            # were embedded by an earlier run the tool correctly does nothing, and
            # "no new rows" is then success. What must hold either way is that a
            # shard RAN to completion and that face data exists at all.
            $before = Count-FaceRows
            $mark = (Get-Item $log).Length
            python -u "$repo\stages\06_faces\faces_embed.py" --thumbs D:\_thumbs `
                   --store D:\_enrichment --shard 0/3 --limit 15 *>> $log
            $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
            try { $null = $fs.Seek($mark, 'Begin'); $out = (New-Object IO.StreamReader($fs)).ReadToEnd() }
            finally { $fs.Dispose() }
            $after = Count-FaceRows
            if ($out -notmatch 'shard \d+ done|images to look at') {
                Say '  faces_embed did not report finishing a shard'
                return $false
            }
            if ($after -le 0) { Say '  no face rows exist anywhere after running'; return $false }
            Say "  shard ran, face rows $before -> $after"
            return $true
        } `
        -Start {
            # Stale shard logs would poison the postcondition, which reads each
            # shard's own "images to look at" line - a leftover log from a
            # different shard count reports thousands outstanding for ever.
            Remove-Item 'D:\_PhotoAudit\faces-*.log' -ErrorAction SilentlyContinue
            Say 'faces: ONE shard (measured: 1 is 1.5x faster than 2 or 3 here)'
            $jobs = @(Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
                '-u', "$repo\stages\06_faces\faces_embed.py", '--thumbs', 'D:\_thumbs',
                '--store', 'D:\_enrichment', '--shard', "0/1"
            ) -RedirectStandardOutput 'D:\_PhotoAudit\faces-0.log' `
              -RedirectStandardError  'D:\_PhotoAudit\faces-0.err')
            Say ("face shard: " + ($jobs.Id -join ', '))
            return $jobs
        } `
        -Progress { Count-FaceRows } `
        -Verify {
            # Re-derives embeddings from the thumbnails and compares. NOT a
            # shape check: every shape check passed on the file that was wrong
            # for five hours. Exit 2 means "too early to tell", which is not a
            # failure - it must not halt a run that has simply not written
            # enough yet.
            $out = & python "$repo\stages\06_faces\verify_faces.py" --sample 6 2>&1 | Out-String
            foreach ($ln in ($out -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            if ($LASTEXITCODE -eq 1) { return $false }
            return $true
        } `
        -Postcondition {
            # "Rows exist" is far too weak. Every shard prints how many images it
            # had to look at; a finished run must have looked at essentially all
            # of them. Without this, killing two of three shards leaves the step
            # reporting success with a third of the library unprocessed - which
            # is exactly what nearly happened while tuning the shard count.
            # ASK THE TOOL WHAT IS LEFT. Do not read a number out of the log.
            #
            # This used to parse "shard 0/1: N images to look at" from faces-0.log
            # - a line printed ONCE AT STARTUP saying how many were outstanding
            # then, and never rewritten. So after a flawless run it still read
            # 47,284, and the postcondition could not pass under any
            # circumstances. It halted the chain at 07:57 on 2026-09-14, two
            # lines after "final verify OK", on a run that had just examined
            # 47,284 images and written 117,866 faces perfectly.
            #
            # Re-invoking faces_embed recomputes the outstanding set from the
            # store and the thumbnail cache and prints what is ACTUALLY left,
            # which is a fact rather than a stale announcement.
            $rows = Count-FaceRows
            if ($rows -le 0) { Say '  no face rows at all'; return $false }
            $out = & python "$repo\stages\06_faces\faces_embed.py" --thumbs D:\_thumbs `
                     --store D:\_enrichment --shard 0/1 --limit 1 2>&1 | Out-String
            $m = [regex]::Match($out, 'images to look at')
            $left = [regex]::Match($out, '([\d,]+) images to look at')
            $n = if ($left.Success) { [int]($left.Groups[1].Value -replace ',', '') } else { -1 }
            Say ("  face rows {0:N0}; images genuinely still outstanding: {1}" -f $rows, $n)
            if ($n -lt 0) { Say '  could not read the outstanding count'; return $false }
            if ($n -gt 200) {
                Say "  $n images were never looked at - this step did not finish"
                return $false
            }
            return $true
        }
    Say 'faces done'
}

if (Should-Run 'D') {
    Invoke-Step -Name 'D sheet' -CheckpointMin 10 `
        -Preflight {
            # The sheet is a join. Both sides must exist, or it produces a
            # confident file with a missing column - which is exactly how
            # OriginPath sat at 0% and Duration at 0.0% without anyone noticing.
            foreach ($f in @('D:\_PhotoAudit\INVENTORY.csv', 'D:\_enrichment\content_tags.csv')) {
                if (-not (Test-Path $f)) { Say "  missing input: $f"; return $false }
                if ((Get-Item $f).Length -lt 1024) { Say "  suspiciously small: $f"; return $false }
            }
            return $true
        } `
        -Start {
            Start-Process python -PassThru -WindowStyle Hidden `
                -ArgumentList @('-u', "$repo\stages\08_index\master_sheet.py") `
                -RedirectStandardOutput 'D:\_PhotoAudit\sheet.out' `
                -RedirectStandardError  'D:\_PhotoAudit\sheet.err'
        } `
        -Progress {
            $t = 'D:\_PhotoAudit\MASTER.csv.tmp'
            if (Test-Path $t) { (Get-Item $t).Length }
            elseif (Test-Path 'D:\_PhotoAudit\MASTER.csv') { (Get-Item 'D:\_PhotoAudit\MASTER.csv').Length }
            else { 0 }
        } `
        -Verify {
            # A sheet is a join, and a broken join produces a complete file with
            # an empty column - which is how OriginPath sat at 0% and Duration at
            # 0.0% while every row looked fine. So: read the newest MASTER.csv
            # and insist the join-dependent columns are actually populated.
            $chk = & python -c @"
import csv, io, sys
p = r'D:\_PhotoAudit\MASTER.csv'
rows = []
with io.open(p, encoding='utf-8', errors='replace', newline='') as f:
    for i, r in enumerate(csv.DictReader(f)):
        rows.append(r)
        if i > 4000: break
if len(rows) < 100:
    print('sheet too small to judge'); sys.exit(2)
def pct(col):
    return 100.0 * sum(1 for r in rows if (r.get(col) or '').strip()) / len(rows)
bad = []
for col, floor in (('Hash', 90), ('Side', 90), ('kind', 50), ('Bytes', 90)):
    v = pct(col)
    print('  {:<8} {:.1f}%'.format(col, v))
    if v < floor: bad.append(col)
if bad: print('join-dependent columns empty: ' + ','.join(bad))
sys.exit(1 if bad else 0)
"@ 2>&1 | Out-String
            foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            return ($LASTEXITCODE -ne 1)
        } `
        -Postcondition {
            Get-Content 'D:\_PhotoAudit\sheet.out' -ErrorAction SilentlyContinue | Add-Content -Path $log
            if (-not (Test-Path 'D:\_PhotoAudit\MASTER.csv')) { Say '  no MASTER.csv'; return $false }
            $age = ((Get-Date) - (Get-Item 'D:\_PhotoAudit\MASTER.csv').LastWriteTime).TotalMinutes
            if ($age -gt 240) { Say "  MASTER.csv is $([int]$age) min old - it was not rewritten"; return $false }
            return $true
        }
    Say 'PHASE 3B COMPLETE. Re-run the receipt sweep now the library is fully classified.'
}