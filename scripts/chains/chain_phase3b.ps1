# After classification: put the sideways thumbnails right, re-judge only those,
# then faces. Sequenced this way because a sideways thumbnail is what both the
# classifier and the face detector read, and re-doing 5,000 files is cheaper
# than accepting 15% fewer faces across the whole library.
$log = 'D:\_PhotoAudit\phase3b.log'
function Say($m) { "$((Get-Date).ToString('HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }
$repo = 'C:\Users\krish\dev\contentarchives'
$env:PYTHONIOENCODING = 'utf-8'
$e = Get-ItemProperty -Path 'HKCU:\Environment'
$env:GOOGLE_API_KEY = $e.GOOGLE_API_KEY

Say 'waiting for classification'
$w = 0
while (-not (Select-String -Path D:\_PhotoAudit\phase3.log -Pattern 'PHASE 3 COMPLETE' -Quiet -ErrorAction SilentlyContinue)) {
    Start-Sleep -Seconds 120; $w++
    if ($w -gt 360) { Say 'STOPPED: classification has not finished after 12 hours'; exit 1 }
}
Say 'classification complete'

Say 'step A: regenerating thumbnails for rotated originals'
python -u "$repo\tools\refix_rotated.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Say "STOPPED: refix_rotated exited $LASTEXITCODE"; exit 1 }

Say 'step B: re-judging only the files whose thumbnail changed'
python -u "$repo\engine\classify_live.py" --thumbs D:\_thumbs --store D:\_enrichment --workers 12 --max-usd 12 --only-list D:\_PhotoAudit\ROTATED-REDO.txt --apply *>> $log
Say 'step B done'

Say 'step C: faces, on images the classifier reports people in'
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
