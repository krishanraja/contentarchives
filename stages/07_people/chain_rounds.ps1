# One naming round: record what Krish answered, then build and GATE the next sheet.
#
#   pwsh -NoProfile -File stages\07_people\chain_rounds.ps1 -Answered 11 -Next 12
#   pwsh -NoProfile -File guards\arm.ps1 -Chain chain_rounds.ps1 -ChainArgs '-Answered 11 -Next 12'
#
# The loop this drives is the only part of the project that cannot be recomputed:
# a person looked at a face and said who it was. Everything else is derived.
#
#   record   record_people.py --sheet   the answers, AND every row he was shown
#            and left blank, which is a REFUSAL and is recorded as one
#   merge    merge_clusters.py          joins the frozen clusters at 0.68
#   rebuild  build_db.py                ~19 min, so the names appear on the photographs
#   sheet    people_sheet.py            the next 60 faces
#   gates    verify_people_sheet.py     every crop belongs to the row it is shown in
#            check_repeats.py           nothing he has already been offered comes back
#
# WHY ONLY THE REBUILD IS SUPERVISED BY Invoke-Step
#
# Invoke-Step supervises LONG work: it takes a progress baseline, launches a
# process, then sleeps until -CheckpointMin minutes have passed before it
# verifies anything. Four of the five steps here finish in seconds to a couple of
# minutes and have no number that meaningfully climbs, so they would exit before
# the first checkpoint ever fired. Wrapping them would produce -Progress blocks
# returning a constant and -Verify blocks that never run: ceremony that reads as
# supervision while supervising nothing, which is the failure mode this project
# keeps hitting (learnings 54, 55). They are gated by exit code instead, and each
# launch carries a `# gate:exempt` reason so the choice is visible in the diff.
#
# The rebuild is different: nineteen minutes, a row count that really does climb,
# and a re-derivation available - take a cluster answer out of the journal and
# ask the half-built index whether that person reached those photographs.
#
# Safe to re-run. record_people is append-only and refuses a cluster id that does
# not exist; merge_clusters never renumbers; build_db writes library.db.tmp and
# renames; the sheet is refused if it already exists.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][int] $Answered,
    [Parameter(Mandatory = $true)][int] $Next,
    [string] $Scratch = 'C:\Users\krish\AppData\Local\Temp\claude\C--Users-krish\86afaf44-6bf1-4455-91e9-df11805be8da\scratchpad'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$log  = 'D:\_PhotoAudit\rounds.log'

function Say($m) {
    $line = "$((Get-Date).ToString('HH:mm:ss'))  $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}

$halt = 'D:\_PhotoAudit\ROUNDS-HALTED.txt'
function Stop-Chain([string] $why) {
    Say "STOPPED: $why"
    "$((Get-Date).ToString('u'))  $why" | Set-Content -Path $halt -Encoding utf8
    Say "wrote $halt - delete it once the cause is fixed, then re-run."
    exit 1
}
if (Test-Path $halt) {
    Say "halted by a previous run, not restarting: $(Get-Content $halt -Raw)"
    exit 0
}

$env:PYTHONIOENCODING = 'utf-8'
. "$repo\guards\steps.ps1"
# A chain that calls Invoke-Step without loading it is worse than one that never
# used it: PowerShell reports an unknown command, carries on, and prints its
# completion message with every step skipped (learning 44).
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load - nothing could be supervised.'
    exit 1
}

# NOT $answered / $next: PowerShell variable names are case-insensitive, so those
# are the very same variables as the [int] parameters, and assigning a path to
# them coerces it back to Int32 - MetadataError on every line, while a preflight
# reading one un-coerced variable still refuses and looks like it worked.
$namesFile    = Join-Path $Scratch "names-r$Answered.txt"
$answeredPage = Join-Path $Scratch "PEOPLE-round$Answered.html"
$nextPage     = Join-Path $Scratch "PEOPLE-round$Next.html"
$journal      = 'D:\_enrichment\answers.csv'
$live         = 'D:\_PhotoAudit\library.db'
$tmp          = "$live.tmp"

Say "round $Answered -> $Next"

# ---- preflight on the whole run, before anything is written ------------------
if (-not (Test-Path $namesFile))    { Stop-Chain "no answers file at $namesFile" }
if (-not (Test-Path $answeredPage)) { Stop-Chain "no sheet at $answeredPage - --sheet is what records a blank row as declined, so without it every refusal is lost" }
if (Test-Path $nextPage)            { Stop-Chain "$nextPage already exists - refusing to overwrite a sheet Krish may have been sent" }
$before = (Get-Item $journal -ErrorAction SilentlyContinue).Length
if (-not $before) { Stop-Chain "no journal at $journal - refusing to record into nothing" }

# ---- 1. record --------------------------------------------------------------
Say '[record] dry run'
# gate:exempt seconds long, no climbing progress number - gated on exit code below
python -u "$repo\stages\07_people\record_people.py" --file $namesFile --sheet $answeredPage *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'the dry run refused something - fix the paste before applying' }

Say '[record] applying'
# gate:exempt seconds long; the postcondition is the journal growing, checked below
python -u "$repo\stages\07_people\record_people.py" --file $namesFile --sheet $answeredPage --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'record failed' }
$after = (Get-Item $journal).Length
if ($after -le $before) { Stop-Chain "the journal did not grow ($before -> $after bytes): nothing was recorded" }
Say ("[record] journal {0:N0} -> {1:N0} bytes" -f $before, $after)

# ---- 2. merge ---------------------------------------------------------------
Say '[merge] joining the frozen clusters at 0.68'
# gate:exempt a couple of minutes, no progress signal; refuses to mix two named people itself
python -u "$repo\stages\06_faces\merge_clusters.py" --threshold 0.68 --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'merge refused - it will not mix two differently-named people' }

# ---- 3. rebuild: the one step long enough to supervise -----------------------
# A cluster answer straight out of the journal, to re-derive against.
# gate:exempt reads one row of a CSV and prints it; starts no work, writes nothing
$probe = & python -c @"
import csv, io, sys
rows = [r for r in csv.DictReader(io.open(r'$journal', encoding='utf-8', newline=''))
        if r.get('field') == 'person' and r.get('scope') == 'cluster' and r.get('value')]
print('{}|{}'.format(rows[-1]['target'], rows[-1]['value']) if rows else '')
"@
$probeCluster, $probePerson = ($probe -split '\|')
if (-not $probeCluster) { Stop-Chain 'no cluster person answer in the journal to verify a rebuild against' }
Say "[rebuild] will re-derive $probeCluster = $probePerson from the half-built index"

function Rows-In([string] $db, [string] $table) {
    if (-not (Test-Path $db)) { return 0 }
    # gate:exempt a mode=ro COUNT(*) - this IS the progress signal the step is supervised by
    $out = & python -c @"
import sqlite3
try:
    c = sqlite3.connect('file:$($db -replace '\\','/')?mode=ro', uri=True)
    try: print(c.execute('select count(*) from $table').fetchone()[0])
    finally: c.close()
except Exception: print(0)
"@
    return [double]($out -replace '[^\d]', '')
}

Invoke-Step -Name 'rebuild' -ExpectedUnits 82193 -CheckpointMin 3 -VerifyEvery 1 -StallStrikes 4 `
    -Preflight {
        # The tmp index is readable mode=ro mid-build (committed rows only) and a
        # reader must not be why the final rename fails (learning 55), so prove
        # the probe query works before committing nineteen minutes to it.
        if (Test-Path $tmp) { Say "  a stale $tmp is present; build_db removes it" }
        $n = Rows-In $live 'files'
        Say ("  the live index holds {0:N0} files" -f $n)
        return ($n -gt 0)
    } `
    -Start {
        Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
            '-u', "$repo\stages\08_index\build_db.py"
        ) -RedirectStandardOutput 'D:\_PhotoAudit\rebuild.out' `
          -RedirectStandardError  'D:\_PhotoAudit\rebuild.err'
    } `
    -Progress {
        # BYTES ON DISK, not committed rows. Rows-In was the first version and the
        # log convicted it: `still at 0` on four of five checkpoints, two of four
        # stall strikes accrued, and `progress 0 -> 0` at the end - because
        # build_db inserts inside one long uncommitted transaction and a mode=ro
        # reader sees only committed rows. I proved exactly that in a probe and
        # then failed to reason from it. On a slower run this would have been
        # KILLED on a false stall at strike 4, throwing away a correct rebuild -
        # a progress signal that cannot move is worse than none, because the
        # supervisor acts on it (learnings 54, 55).
        $n = 0
        foreach ($f in @($tmp, "$tmp-wal")) {
            if (Test-Path $f) { $n += (Get-Item $f).Length }
        }
        return [double]$n
    } `
    -Verify {
        # RE-DERIVE, do not inspect shape: ask the index whether the person named
        # against $probeCluster in the journal actually reached the photographs of
        # that cluster. Row counts climbing prove nothing - a five-hour face run
        # wrote every embedding against the wrong photograph with perfect counts.
        #
        # THE TMP FILE IS GONE BY THE FINAL VERIFY, and the first version of this
        # block only ever looked at $tmp. Invoke-Step always runs -Verify once
        # more after the process exits, by which time build_db has renamed
        # library.db.tmp to library.db - so the connect failed, the block took its
        # PENDING escape hatch, and the ONE verify that gates the whole step
        # passed on "nothing to check yet". Measured: 1 OK, 4 PENDING, and the
        # final one was a PENDING. A check with an escape hatch reports success
        # while measuring nothing (learnings 54, 55).
        #
        # So: whichever database exists, newest first. PENDING is legal ONLY
        # while the tmp build has not reached photo_people yet. A live index with
        # no person rows, or no openable database at all, is WRONG.
        # gate:exempt a mode=ro re-derivation of one journal answer - this IS the correctness check
        $out = & python -c @"
import os, sqlite3
tmp  = r'$tmp'
live = r'$live'
db, building = (tmp, True) if os.path.isfile(tmp) else ((live, False) if os.path.isfile(live) else (None, False))
if db is None:
    print('WRONG no-database'); raise SystemExit
try:
    c = sqlite3.connect('file:' + db.replace(chr(92), '/') + '?mode=ro', uri=True)
except Exception as e:
    print('WRONG cannot-open'); raise SystemExit
try:
    try:
        n = c.execute('select count(*) from photo_people').fetchone()[0]
    except Exception:
        print('PENDING no-table' if building else 'WRONG live-has-no-photo_people'); raise SystemExit
    if not n:
        print('PENDING empty' if building else 'WRONG live-has-no-person-rows'); raise SystemExit
    hits = c.execute(
        'select count(*) from photo_people p join tags t on t.hash = p.hash '
        "where t.tag = 'cluster' and t.value = ? and p.person = ?",
        ('$probeCluster', '''$probePerson''')).fetchone()[0]
    print(('OK ' if hits else 'WRONG ') + os.path.basename(db))
finally:
    c.close()
"@
        Add-Content -Path $log -Value "  verify: $out"
        if ($out -match 'WRONG') {
            Say "  re-derivation FAILED ($out): $probeCluster without $probePerson"
            return $false
        }
        return $true
    } `
    -Postcondition {
        # Ask the LIVE index, after the rename, not the log that announced it.
        $files = Rows-In $live 'files'
        $people = Rows-In $live 'photo_people'
        Say ("  live index: {0:N0} files, {1:N0} person rows" -f $files, $people)
        if (Test-Path $tmp) {
            Say "  $tmp still exists - the swap did not happen. NOTHING IS LOST; see promote() in build_db.py."
            return $false
        }
        return (($files -gt 0) -and ($people -gt 0))
    } | Out-Null

# ---- 4. the next sheet, and the two gates Krish asked for -------------------
Say "[sheet] building round $Next"
# gate:exempt a minute or two, and the two gates below are the real check
python -u "$repo\stages\07_people\people_sheet.py" --top 60 --out $nextPage *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'the sheet failed to build' }
if (-not (Test-Path $nextPage)) { Stop-Chain "people_sheet exited 0 but wrote no $nextPage" }

Say '[gate] every crop belongs to the row it is shown in'
# gate:exempt seconds; this IS a verifier, and its exit code is the gate
python -u "$repo\stages\07_people\verify_people_sheet.py" --page $nextPage *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'a crop does not belong to its row - Krish must not see this sheet' }

Say '[gate] nothing already offered comes back'
# gate:exempt seconds; this IS a verifier, and its exit code is the gate
python -u "$repo\stages\07_people\check_repeats.py" $Scratch $nextPage *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain "round $Next re-shows a row Krish has already been offered" }

Say "ROUND $Next READY: $nextPage"
exit 0
