# Resume phase 3 from wherever the store got to, and run through to the end of
# phase 3b, in ONE process.
#
# WHY THIS FILE EXISTS SEPARATELY FROM chain_phase3.ps1
#
# On 2026-09-12 at 12:56:00 the agent session ended and the classifier died in
# the same second, at 53,325 of 79,017. It had been launched with
# `Start-Process pwsh -WindowStyle Hidden`, which hides a window but does NOT
# leave the process tree - so when the session's tree was killed, the work went
# with it, along with both waiting chains. Hidden is not detached.
#
# Launch this with scripts/chains/arm.ps1, which registers it as a SCHEDULED
# TASK. Task Scheduler owns the process, not the console, so it survives the
# session ending, the CLI closing, and logging out. That is the actual fix.
#
# Nothing here repeats paid work: classify_live skips any hash this model has
# already tagged, so a re-run resumes and costs only what is left. Step 3a
# (build_inventory) finished at 04:59 and is not repeated.
$log  = 'D:\_PhotoAudit\phase3.log'
$repo = 'C:\Users\krish\dev\contentarchives'
function Say($m) { "$((Get-Date).ToString('HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }

$env:PYTHONIOENCODING = 'utf-8'
$e = Get-ItemProperty -Path 'HKCU:\Environment'
$env:GOOGLE_API_KEY = $e.GOOGLE_API_KEY
if (-not $env:GOOGLE_API_KEY) { Say 'STOPPED: GOOGLE_API_KEY not in HKCU\Environment'; exit 1 }

Say 'RESUMED after the 12:56 session-death. Ceiling $20 on top of the $24.11 already spent.'

# --- the rest of phase 3 -----------------------------------------------------
Say 'step 3b (resumed): classifying the remaining ~25,695 files'
python -u "$repo\engine\classify_live.py" --thumbs D:\_thumbs --store D:\_enrichment --workers 12 --max-usd 20 --apply *>> $log
if ($LASTEXITCODE -ne 0) { Say "WARNING: classify_live exited $LASTEXITCODE - the store keeps what it wrote; re-running resumes" }
Say 'step 3b done'

Say 'step 3c: rebuilding MASTER.csv and scoring coverage'
python -u "$repo\tools\master_sheet.py" *>> $log
Say 'PHASE 3 COMPLETE. Review the coverage table above, then decide segmentation.'

# --- phase 3b, inlined so there is one process to keep alive, not two ---------
Say 'step A: regenerating thumbnails for rotated originals'
python -u "$repo\tools\refix_rotated.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Say "STOPPED: refix_rotated exited $LASTEXITCODE"; exit 1 }

Say 'step B: re-judging only the files whose thumbnail changed'
python -u "$repo\engine\classify_live.py" --thumbs D:\_thumbs --store D:\_enrichment --workers 12 --max-usd 12 --only-list D:\_PhotoAudit\ROTATED-REDO.txt --apply *>> $log
Say 'step B done'

Say 'step C: faces, six shards'
$jobs = @()
foreach ($i in 0..5) {
    $jobs += Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
        '-u', "$repo\engine\faces_embed.py", '--thumbs', 'D:\_thumbs',
        '--store', 'D:\_enrichment', '--shard', "$i/6"
    ) -RedirectStandardOutput "D:\_PhotoAudit\faces-$i.log" -RedirectStandardError "D:\_PhotoAudit\faces-$i.err"
}
Say ("face shards: " + ($jobs.Id -join ', '))
$jobs | Wait-Process
Say 'faces done'

Say 'step D: rebuilding the sheet'
python -u "$repo\tools\master_sheet.py" *>> $log
Say 'PHASE 3B COMPLETE. Re-run the receipt sweep now the library is fully classified.'
