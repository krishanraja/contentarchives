# The family app's nightly catch-up on the library machine. OPTIONAL by design:
# the app runs from Google Drive and the cloud index with this machine off
# (Krish, 2026-10-04: "always on and accessible, no reliance on a local drive").
# When this machine is on, this makes what the family said permanent and lets
# the library's new knowledge reach the app.
#
#   pwsh -NoProfile -File stages\13_app\chain_app_sync.ps1
#   pwsh -NoProfile -File guards\arm.ps1 -Chain chain_app_sync.ps1      # nightly task
#
#   pull     pull_answers.py --apply   app answers older than 10 min -> answers.csv,
#                                      under each relative's name; G: backup refreshed
#   merge    merge_clusters.py         a new name reaches the group's sibling clusters
#   rebuild  build_db.py               the names and places land on the photographs
#   seed     seed_index.py --apply     the cloud index re-seeded and reconciled;
#                                      exits non-zero unless the cloud's own count matches
#
# WHY NO STEP IS SUPERVISED BY Invoke-Step
#
# Three steps take seconds to a couple of minutes with no number that climbs;
# wrapping them would be ceremony that reads as supervision (chain_rounds.ps1
# says why at length). The rebuild is long, and chain_rounds.ps1 supervises it
# properly - this chain does NOT duplicate that block: it runs the rebuild
# exempt, gated on exit code and on the live index actually being replaced,
# and a failed rebuild stops the chain before anything is uploaded. Every step
# is safe to re-run.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$log  = 'D:\_PhotoAudit\app-sync.log'
$halt = 'D:\_PhotoAudit\APP-SYNC-HALTED.txt'

function Say($m) {
    $line = "$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))  $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}
function Stop-Chain([string] $why) {
    Say "STOPPED: $why"
    "$((Get-Date).ToString('u'))  $why" | Set-Content -Path $halt -Encoding utf8
    exit 1
}
if (Test-Path $halt) {
    Say "halted by a previous run, not restarting: $(Get-Content $halt -Raw)"
    exit 0
}
$env:PYTHONIOENCODING = 'utf-8'
. "$repo\guards\steps.ps1"
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load.'
    exit 1
}
if (-not $env:SUPABASE_URL -or -not $env:SUPABASE_SERVICE_ROLE_KEY) {
    Stop-Chain 'SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set for this task'
}

Say '[pull] app answers -> journal'
# gate:exempt seconds long, no climbing number; it marks no cloud row unless the ingest exits 0
python -u "$repo\stages\13_app\pull_answers.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'pull failed - the cloud rows stay new and will be retried' }

Say '[merge] names reach sibling clusters'
# gate:exempt a couple of minutes, no progress signal; a refusal to mix two named people is a WARNING here
python -u "$repo\stages\06_faces\merge_clusters.py" --threshold 0.68 --apply *>> $log
if ($LASTEXITCODE -ne 0) { Say '[merge] refused (two names in one group) - continuing; name_clusters.py --like will show it' }

$live = 'D:\_PhotoAudit\library.db'
$was = (Get-Item $live).LastWriteTimeUtc
Say '[rebuild] build_db.py'
# gate:exempt supervised in chain_rounds.ps1; here gated on exit code AND the live index being replaced, below
python -u "$repo\stages\08_index\build_db.py" *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'rebuild failed - nothing uploaded' }
if ((Get-Item $live).LastWriteTimeUtc -le $was) { Stop-Chain 'build_db exited 0 but library.db was not replaced' }

Say '[seed] cloud index'
# gate:exempt exits non-zero unless the cloud's own count equals the share set
python -u "$repo\stages\13_app\seed_index.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'seed did not verify against the cloud' }
Say 'APP SYNC COMPLETE'
