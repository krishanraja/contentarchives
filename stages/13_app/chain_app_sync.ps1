# Refresh the BACKUP drive from the cloud and from H:. OPTIONAL by design: the
# app, its index and the family's record all live in the cloud and run with
# this machine off (Krish, 2026-10-04: "always on and accessible, no reliance
# on a local drive"; 2026-10-16: "The external D (currently F) Drive should
# just be a backup, nothing should rely on this external drive, everything
# should be able to be done on H drive"). When the drive is plugged in, this
# brings its copy up to date. When it is not, this says so and stops cleanly.
#
#   pwsh -NoProfile -File stages\13_app\chain_app_sync.ps1
#   pwsh -NoProfile -File guards\arm.ps1 -Chain chain_app_sync.ps1      # nightly task
#
#   pull     pull_answers.py --apply   app answers older than 10 min -> answers.csv,
#                                      under each relative's name; G: backup refreshed
#   merge    merge_clusters.py         a new name reaches the group's sibling clusters
#   rebuild  build_db.py               the names and places land on the photographs
#   backup   backup_to_drive.py        the cloud's nightly export of the family's record,
#                                      and every photograph H: has that this drive lacks,
#                                      each md5-checked; never overwrites, never deletes
#   seed     seed_index.py --apply     ONLY with -Seed: the cloud index re-seeded and
#                                      reconciled from this machine
#
# THE DRIVE IS FOUND BY WHAT IS ON IT, NOT BY ITS LETTER
#
# Every script here says D:. Windows hands the same drive a different letter
# when it is plugged in after another (it came back as F: on 2026-10-16), so the
# first of D: to Z: holding _PhotoAudit\library.db and _enrichment\answers.csv
# is the backup drive, mapped to D: (subst) for this run only and unmapped
# before the run ends, whichever way it ends.
#
# WHY SEED IS OFF UNLESS ASKED FOR
#
# Since 2026-10-05 the cloud builds its own index from Drive (cloud_enrich.py,
# the one writer), and it holds photographs this machine never had: everything
# that reached Drive straight from a phone, and the Personal photographs it
# shows. seed_index.py empties the cloud's faces, clusters, people and queue and
# refills them from this library alone. Measured 2026-10-16, that would have
# deleted 9,230 faces on 3,724 photographs that exist only in the cloud. Run it
# by hand with -Seed only after making sure the cloud has nothing it lacks.
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
param([switch] $Seed)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$script:mapped = $false
function Test-Backup([string] $root) {
    # plain strings, not Join-Path: Join-Path throws when the drive does not exist,
    # which is the very case this is here to answer quietly
    (Test-Path -LiteralPath ($root + '_PhotoAudit\library.db')) -and (Test-Path -LiteralPath ($root + '_enrichment\answers.csv'))
}
function Unmap-Backup {
    if ($script:mapped) { subst D: /d | Out-Null; $script:mapped = $false }
}
# an unexpected error anywhere below still leaves no mapping behind
trap { Unmap-Backup; break }
if (-not (Test-Backup 'D:\')) {
    $found = $null
    foreach ($l in [char[]](69..90)) {                     # E: .. Z:
        if (Test-Backup ('{0}:\' -f $l)) { $found = $l; break }
    }
    if (-not $found) {
        Write-Host 'backup drive not connected - nothing to refresh (nothing waits on it)'
        exit 0
    }
    if (Test-Path 'D:\') {
        Write-Host ('the backup drive is {0}: but D: belongs to another drive - give the backup drive the letter D: in Disk Management' -f $found)
        exit 0
    }
    subst D: ('{0}:\' -f $found) | Out-Null
    $script:mapped = $true
    if (-not (Test-Backup 'D:\')) {
        Unmap-Backup
        Write-Host ('could not map {0}: to D:' -f $found)
        exit 1
    }
}

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
    Unmap-Backup
    exit 1
}
if ($script:mapped) { Say "backup drive found at another letter; mapped to D: for this run" }
if (Test-Path $halt) {
    Say "halted by a previous run, not restarting: $(Get-Content $halt -Raw)"
    Unmap-Backup
    exit 0
}
$env:PYTHONIOENCODING = 'utf-8'
. "$repo\guards\steps.ps1"
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load.'
    Unmap-Backup
    exit 1
}
# The archive's own names first, never mixed with the generic pair (cloud.py
# says why): the generic names can hold another project on this machine.
$own = $env:ARCHIVES_SUPABASE_URL -or $env:ARCHIVES_SUPABASE_SERVICE_ROLE_KEY
$creds = $env:SUPABASE_URL -and $env:SUPABASE_SERVICE_ROLE_KEY
if ($own) { $creds = $env:ARCHIVES_SUPABASE_URL -and $env:ARCHIVES_SUPABASE_SERVICE_ROLE_KEY }
if (-not $creds) {
    Stop-Chain 'ARCHIVES_SUPABASE_URL / ARCHIVES_SUPABASE_SERVICE_ROLE_KEY are not both set for this task'
}

Say '[pull] app answers -> journal'
# gate:exempt seconds long, no climbing number; it marks no cloud row unless the ingest exits 0
python -u "$repo\stages\13_app\pull_answers.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'pull failed - the cloud rows stay new and will be retried' }

Say '[merge] names reach sibling clusters'
# 0.70, not chain_rounds' 0.68 (Krish, 2026-10-16): at 0.68 two groups put
# Shilu with Bharti and with Jyoti, and all five labels were confirmed right,
# so the faces only look alike. 0.70 is the lowest threshold with no such group.
# gate:exempt a couple of minutes, no progress signal; a refusal to mix two named people is a WARNING here
python -u "$repo\stages\06_faces\merge_clusters.py" --threshold 0.70 --apply *>> $log
# A non-zero exit is EITHER a refusal to mix two named people OR a failure (on
# 2026-10-16 a missing face-emb.npy, since removed as an input, and this line
# called that traceback a refusal). Say which it might be, and point at the log.
if ($LASTEXITCODE -ne 0) { Say "[merge] exited $LASTEXITCODE - continuing; read app-sync.log: a refusal (two names in one group; name_clusters.py --like shows it) or a failure (a STOPPING line or a traceback)" }

$live = 'D:\_PhotoAudit\library.db'
$was = (Get-Item $live).LastWriteTimeUtc
Say '[rebuild] build_db.py'
# gate:exempt supervised in chain_rounds.ps1; here gated on exit code AND the live index being replaced, below
python -u "$repo\stages\08_index\build_db.py" *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'rebuild failed - nothing uploaded' }
if ((Get-Item $live).LastWriteTimeUtc -le $was) { Stop-Chain 'build_db exited 0 but library.db was not replaced' }

Say '[backup] the cloud record and new photographs from H:'
# gate:exempt bounded by --max-gb per run; every file is md5-checked against Drive's own, journalled, never overwritten
python -u "$repo\stages\13_app\backup_to_drive.py" --apply --drive D:\ *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'the backup failed a check (a sha256 or md5 mismatch) - read app-sync.log' }

if (-not $Seed) {
    Say '[seed] skipped: the cloud builds its own index; pass -Seed only on purpose'
    Say 'APP SYNC COMPLETE'
    Unmap-Backup
    exit 0
}
Say '[seed] cloud index'
# gate:exempt exits non-zero unless the cloud's own count equals the share set
python -u "$repo\stages\13_app\seed_index.py" --apply *>> $log
if ($LASTEXITCODE -ne 0) { Stop-Chain 'seed did not verify against the cloud' }
Say 'APP SYNC COMPLETE'
Unmap-Backup
