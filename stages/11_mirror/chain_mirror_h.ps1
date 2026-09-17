# Mirror the library to H:, supervised, and survive being killed.
#
#     pwsh -NoProfile -File guards\arm.ps1 -Chain chain_mirror_h.ps1
#     pwsh -NoProfile -File guards\arm.ps1 -Status
#     pwsh -NoProfile -File guards\arm.ps1 -Stop
#
# 82,112 files and 925 GB is days of work on a machine that kills long jobs
# under memory pressure. So this leans entirely on two things being true:
#
#   mirror_to_h.py journals every file it writes, APPEND-ONLY, and skips what
#   the journal names on the next run. A kill costs the file in flight.
#
#   arm.ps1 registers the task with RestartCount 99, so a kill is followed by a
#   restart about a minute later, which resumes.
#
# The Postcondition here is deliberately "nothing left to send". While files
# remain, the step FAILS and the task exits non-zero - which is what makes the
# Task Scheduler restart it. That reads oddly and is the point: a partial
# upload is not a finished one, and the only honest way to say so is to fail.
$ErrorActionPreference = 'Stop'
$log = 'D:\_PhotoAudit\mirror-h-chain.log'
function Say($m) { "$((Get-Date).ToString('HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py   = "$repo\stages\11_mirror\mirror_to_h.py"
$journal = 'D:\_PhotoAudit\h-mirror.csv'

. "$repo\guards\steps.ps1"

# A supervisor that failed to load is indistinguishable from one that approved
# everything, because PowerShell reports an unknown command and carries on
# (learning 44).
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load - nothing could be supervised.'
    exit 1
}
function Stop-Chain([string] $why) { Say "STOPPED: $why"; exit 1 }

function Journalled { if (Test-Path $journal) { (Get-Content $journal | Measure-Object -Line).Lines } else { 0 } }

# Count what is left WITHOUT launching anything.
#
# This used to shell out to `python mirror_to_h.py --status` and parse the
# output. test_chain_gating.py refused the chain for it, and correctly: every
# launch inside a chain must sit within Invoke-Step, which forces a preflight, a
# progress signal and a postcondition. A bare `& python` in a helper called by
# the Postcondition is work that never proved it works.
#
# The two numbers are already on disk: the index says how many files there are,
# the journal says how many landed. Reading them is a status check, not work.
function Remaining {
    if (-not (Test-Path $journal)) { return -1 }
    $written = @(Import-Csv $journal | Where-Object { $_.outcome -eq 'written' -or $_.outcome -eq 'already-present' }).Count
    # The index is the denominator, minus what mirror_to_h itself excludes as
    # implausibly large (over 20 GB - the 101 GB null-byte .jpg).
    # The denominator comes from INVENTORY.csv, not from library.db.
    #
    # The first version shelled out to sqlite3.exe, which is NOT on PATH on this
    # machine - so Remaining would have returned -1 on every call, the
    # Postcondition would have failed, and the task would have restarted in a
    # loop forever while reporting "could not read the remaining count". A
    # dependency that is absent is worse than one that is wrong, because the
    # failure looks like the job rather than the check.
    $inv = 'D:\_PhotoAudit\INVENTORY.csv'
    if (-not (Test-Path $inv)) { return -1 }
    $total = (@(Get-Content $inv).Count) - 1      # minus the header
    if ($total -lt 0) { return -1 }
    return [Math]::Max(0, $total - $written)
}

Say "mirror to H: starting. journalled so far: $(Journalled) row(s)"

Invoke-Step -Name 'mirror-to-h' -ExpectedUnits 82112 -CheckpointMin 15 -VerifyEvery 2 `
    -Preflight {
        if (-not (Test-Path 'H:\My Drive')) { Say '  H: is not mounted'; return $false }
        if (-not (Test-Path 'D:\_PhotoAudit\library.db')) { Say '  no index'; return $false }
        # Write ONE file before committing to 925 GB. thumbnail.py produced
        # sideways thumbnails for weeks because nothing ever looked at one it
        # made; the same mistake here would be 82,000 files of something.
        $out = & python -u $py --limit 1 2>&1 | Out-String
        foreach ($ln in ($out -split "`n" | Where-Object { $_ -match 'written|failed|LOCAL WRITE' })) { Say "    $($ln.Trim())" }
        if ($out -notmatch 'written\s+[1-9]' -and $out -notmatch 'nothing left to send') {
            Say '  the one-file probe did not write anything'; return $false
        }
        $free = (Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='H:'").FreeSpace / 1GB
        Say ("  H: cache free: {0:N1} GB" -f $free)
        if ($free -lt 45) { Say '  cache too tight to start'; return $false }
        return $true
    } `
    -Start {
        Say 'launching the full mirror (resumes from the journal)'
        return Start-Process python -PassThru -WindowStyle Hidden `
            -ArgumentList @('-u', $py) `
            -RedirectStandardOutput 'D:\_PhotoAudit\mirror-h.out' `
            -RedirectStandardError  'D:\_PhotoAudit\mirror-h.err'
    } `
    -Progress { Journalled } `
    -Verify {
        # RE-DERIVE from the source, never from the destination: reading a file
        # back through the mount hydrates a placeholder and fills C: (learning
        # 5), and a cache read-back is what "verified" 140.62 GB that the cloud
        # did not have (learning 25).
        $chk = & python -u -c @"
import csv, hashlib, io, os, random, sys
J = r'D:\_PhotoAudit\h-mirror.csv'
rows = [r for r in csv.DictReader(io.open(J, encoding='utf-8', newline='')) if r.get('outcome') == 'written' and r.get('blake2b')]
if not rows:
    print('no journalled rows yet'); sys.exit(2)
random.seed(0)
bad = 0
for r in random.sample(rows, min(4, len(rows))):
    src = r['source']
    try:
        d = hashlib.blake2b(digest_size=32)
        with open('\\\\?\\' + src, 'rb', buffering=0) as f:
            for b in iter(lambda: f.read(8 << 20), b''):
                d.update(b)
        got = d.hexdigest()
    except OSError as e:
        print('  unreadable source %s: %s' % (os.path.basename(src), e)); bad += 1; continue
    if got != r['blake2b']:
        print('  MISMATCH %s: journal %s, source %s' % (os.path.basename(src), r['blake2b'][:16], got[:16])); bad += 1
print('re-derived %d sampled row(s), %d wrong' % (min(4, len(rows)), bad))
sys.exit(1 if bad else 0)
"@ 2>&1 | Out-String
        foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $($ln.Trim())" }
        return ($LASTEXITCODE -ne 1)
    } `
    -Postcondition {
        $left = Remaining
        Say "  files still to send: $left"
        if ($left -lt 0) { Say '  could not read the remaining count'; return $false }
        if ($left -gt 0) {
            Say '  partial upload - failing on purpose so the task restarts and resumes'
            return $false
        }
        return $true
    }

Say 'every file is journalled as written.'
Say 'NEXT, and it is NOT done until this passes:'
Say '  the bytes are in the Drive CACHE and upload behind it. Verification'
Say '  needs the server-side md5Checksum from the Drive API, which needs a'
Say '  Drive-scoped gcloud login. Until then this is uploaded, not verified.'
