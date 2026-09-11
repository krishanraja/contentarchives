# Phase 3, chained onto phase 2: rebuild the technical metadata, then classify
# the whole library, then rebuild the sheet and print the score.
#
# Krish authorised running to the end of phase 3 autonomously on 2026-09-11,
# and the model choice (Gemini 3.1 Flash-Lite) on the same day off the back of
# the bake-off. The spend ceiling below is a brake, not a budget: it stops on
# MEASURED spend, so a pricing surprise halts the run instead of discovering it
# on a statement.
$log = 'D:\_PhotoAudit\phase3.log'
function Say($m) { "$((Get-Date).ToString('HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }

$repo = 'C:\Users\krish\dev\contentarchives'
$env:PYTHONIOENCODING = 'utf-8'
$e = Get-ItemProperty -Path 'HKCU:\Environment'
$env:GOOGLE_API_KEY = $e.GOOGLE_API_KEY
if (-not $env:GOOGLE_API_KEY) { Say 'STOPPED: GOOGLE_API_KEY not in HKCU\Environment'; exit 1 }

Say 'waiting for the thumbnail phase to finish'
$waited = 0
while (-not (Select-String -Path D:\_PhotoAudit\thumbs-chain.log -Pattern '^\S+\s+DONE\.' -Quiet -ErrorAction SilentlyContinue)) {
    Start-Sleep -Seconds 60
    $waited += 1
    if ($waited -gt 900) { Say 'STOPPED: thumbnails have not finished after 15 hours.'; exit 1 }
}
$thumbs = (Get-ChildItem D:\_thumbs -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
Say "thumbnails present: $thumbs"
if ($thumbs -lt 60000) {
    Say "STOPPED: only $thumbs thumbnails. Expected ~97,000. Classifying now would"
    Say 'pay to label a fraction of the library and report it as done.'
    exit 1
}

# 1. Technical metadata. Feeds eight columns of MASTER.csv and is currently
#    68,042 rows from before the migration. --video is the slow flag and is
#    what fills Duration, Width and Height for the videos.
Say 'step 3a: rebuilding INVENTORY.csv with video probing'
python -u "$repo\scripts\build_inventory.py" --video *>> $log
if ($LASTEXITCODE -ne 0) { Say "WARNING: build_inventory exited $LASTEXITCODE - continuing to classification anyway, it is an independent input" }
Say 'step 3a done'

# 2. The enrichment pass itself.
Say 'step 3b: classifying with gemini-3.1-flash-lite, 12 threads, ceiling $55'
python -u "$repo\engine\classify_live.py" --thumbs D:\_thumbs --store D:\_enrichment --workers 12 --max-usd 55 --apply *>> $log
if ($LASTEXITCODE -ne 0) { Say "WARNING: classify_live exited $LASTEXITCODE - the store keeps what it wrote; re-running resumes" }
Say 'step 3b done'

# 3. The number this is all for.
Say 'step 3c: rebuilding MASTER.csv and scoring coverage'
python -u "$repo\tools\master_sheet.py" *>> $log
Say 'PHASE 3 COMPLETE. Review the coverage table above, then decide segmentation.'
