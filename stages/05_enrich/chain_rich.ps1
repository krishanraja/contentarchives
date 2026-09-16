# The description pass, run ALONGSIDE faces rather than after it.
#
# Krish asked for richness on 2026-09-13, having seen that the median `subject`
# was four words - "rocky coastal cliff" - which is enough to find a photograph
# and not enough to read one. This pass adds a real description, an object list,
# the activity, any legible text, the occasion and the mood.
#
# It REPLACES NOTHING. Its own source id (...-rich), its own field names, its own
# resume marker. The four-word subject stays exactly where it is, so a pass that
# goes wrong costs money and not the work already paid for.
#
# WHY IT CAN SHARE THE MACHINE WITH FACES
#
# Faces is CPU-bound and pinned at 100%; this is network-bound, waiting on an
# API. They contend for memory rather than for cores, which is why the worker
# count is 5 and not 12 - memory pressure is what kills long jobs on this box.
# Measured in the pilot at ~2 files/sec with 4 workers WHILE faces was running.
#
# COST, MEASURED NOT ESTIMATED
#
# Pilot: 120 files, 0 failures, $0.07 - so $0.000583 a file and about $46 for the
# library. The earlier $27 figure was the cheap pass; descriptions cost more in
# output tokens. --max-usd stops on MEASURED spend.
param([double] $MaxUsd = 55.0, [int] $Workers = 5)

$log  = 'D:\_PhotoAudit\rich.log'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
function Say($m) {
    $line = "$((Get-Date).ToString('HH:mm:ss'))  $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}

$halt = 'D:\_PhotoAudit\RICH-HALTED.txt'
function Stop-Chain([string] $why) {
    Say "STOPPED: $why"
    "$((Get-Date).ToString('u'))  $why" | Set-Content -Path $halt -Encoding utf8
    Say "wrote $halt - delete it once the cause is fixed, then re-arm."
    exit 1
}
if (Test-Path $halt) {
    Say "halted by a previous run, not restarting: $(Get-Content $halt -Raw)"
    exit 0
}

$env:PYTHONIOENCODING = 'utf-8'
$e = Get-ItemProperty -Path 'HKCU:\Environment'
$env:GOOGLE_API_KEY = $e.GOOGLE_API_KEY
if (-not $env:GOOGLE_API_KEY) { Say 'STOPPED: GOOGLE_API_KEY not in HKCU\Environment'; exit 1 }

. "$PSScriptRoot\steps.ps1"
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load - nothing could be supervised.'
    exit 1
}

$tags = 'D:\_enrichment\content_tags.csv'
function Count-RichRows {
    if (-not (Test-Path $tags)) { return 0 }
    (Select-String -Path $tags -Pattern '-rich,' -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count
}
function Get-RichOutstanding {
    # gate:exempt read-only dry run, no --apply, seconds: this IS the preflight
    $out = & python "$repo\stages\05_enrich\classify_live.py" --thumbs D:\_thumbs `
             --store D:\_enrichment --rich 2>&1 | Out-String
    $m = [regex]::Match($out, 'to classify:\s*([\d,]+) files')
    if (-not $m.Success) { return -1 }
    return [int]($m.Groups[1].Value -replace ',', '')
}

Say '=== description pass start (safe to restart; resumes on the store) ==='

for ($try = 1; $try -le 40; $try++) {
    $left = Get-RichOutstanding
    if ($left -lt 0) { Stop-Chain 'could not read the outstanding count' }
    if ($left -eq 0) { Say 'nothing outstanding'; break }
    Say ("attempt {0}: {1:N0} files still to describe" -f $try, $left)

    Invoke-Step -Name "rich a$try" -ExpectedUnits ($left * 5.3) -CheckpointMin 15 `
        -VerifyEvery 4 -StallStrikes 3 `
        -Preflight {
            # Prove the RICH prompt is really what goes out, on three files,
            # before spending $46 finding out otherwise. call() used to read the
            # prompt from a global while --rich chose a different one and passed
            # it nowhere; that would have produced a complete, plausible result
            # full of four-word labels.
            $before = Count-RichRows
            python -u "$repo\stages\05_enrich\classify_live.py" --thumbs D:\_thumbs `
                   --store D:\_enrichment --rich --workers 2 --limit 3 `
                   --max-usd 0.5 --apply *>> $log
            if ((Count-RichRows) -le $before) {
                Say '  the three-file probe wrote nothing'
                return $false
            }
            $chk = & python "$repo\stages\05_enrich\verify_rich.py" --sample 6 2>&1 | Out-String
            foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            return ($LASTEXITCODE -ne 1)
        } `
        -Start {
            Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
                '-u', "$repo\stages\05_enrich\classify_live.py", '--thumbs', 'D:\_thumbs',
                '--store', 'D:\_enrichment', '--rich',
                '--workers', "$Workers", '--max-usd', "$MaxUsd", '--apply'
            ) -RedirectStandardOutput 'D:\_PhotoAudit\rich.out' `
              -RedirectStandardError  'D:\_PhotoAudit\rich.err'
        } `
        -Progress { Count-RichRows } `
        -Verify {
            # Are these DESCRIPTIONS or labels? The only question that separates
            # a correct $46 from a wasted one, and no count can answer it.
            $chk = & python "$repo\stages\05_enrich\verify_rich.py" --sample 30 2>&1 | Out-String
            foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
            return ($LASTEXITCODE -ne 1)
        } `
        -Postcondition {
            Get-Content 'D:\_PhotoAudit\rich.out' -Tail 40 -ErrorAction SilentlyContinue |
                Add-Content -Path $log
            $o = Get-Content 'D:\_PhotoAudit\rich.out' -Raw -ErrorAction SilentlyContinue
            if ($o -match 'CEILING REACHED') {
                Stop-Chain 'the description pass hit its spend ceiling. Raise it deliberately.'
            }
            if ($o -match 'finished in') { return $true }
            Say '  the pass ended without finishing - it will be retried'
            return $true      # a kill is not a failure here; the loop resumes it
        }
}

$left = Get-RichOutstanding
if ($left -gt 0) { Stop-Chain "gave up with $left files still undescribed" }
# gate:exempt read-only final verification, writes nothing, cannot spend
python -u "$repo\stages\05_enrich\verify_rich.py" --sample 40 *>> $log
Say 'RICH PASS COMPLETE. Rebuild the sheet and library.db to pick the new fields up.'
