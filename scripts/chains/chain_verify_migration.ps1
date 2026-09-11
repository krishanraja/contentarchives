# Wait for the running copy, then carry the extras and verify - with no human in
# the loop. The copy is disk-bound and so is the verification; the only latency
# worth removing is the gap between one finishing and somebody noticing.
$log = 'D:\_PhotoAudit\migrate-chain.log'
function Say($m) { "$((Get-Date).ToString('HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }

Say 'waiting for the copy to finish'
while (Get-Process python -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 30 }

if (-not (Select-String -Path D:\_PhotoAudit\migrate.log -Pattern 'copy finished' -Quiet)) {
    Say 'STOPPED: the copy process exited without printing "copy finished".'
    Say 'It died rather than completed. Re-run migrate_library.py --to E: --apply'
    Say '(it resumes). Not running verify against an incomplete copy.'
    exit 1
}
Say 'copy finished cleanly'

$env:PYTHONIOENCODING = 'utf-8'
Say 'step 2: carrying _PhotoAudit, _enrichment, _thumbs'
python -u D:\_PhotoAudit\scripts\migrate_library.py --to E: --extras --apply *>> $log
if ($LASTEXITCODE -ne 0) { Say "STOPPED: extras failed ($LASTEXITCODE). Do not swap drive letters."; exit 1 }

Say 'step 1: verifying every file by reading E: back'
python -u D:\_PhotoAudit\scripts\migrate_library.py --to E: --verify *>> $log
if ($LASTEXITCODE -ne 0) {
    Say 'STOPPED: VERIFICATION FAILED. Do not swap drive letters. Do not touch'
    Say 'the source. See MIGRATION-VERIFY.csv for the files that did not match.'
    exit 1
}
Say 'VERIFIED. Both copies exist and the new one is proven byte for byte.'
Say 'Next, and it needs Krish: the elevated drive-letter swap, RESUME.md step 3.'
