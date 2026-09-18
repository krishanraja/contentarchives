# Wait for the H: ingest, then build every missing thumbnail, in parallel.
# Thumbnailing is CPU-bound (Pillow resize, ffmpeg decode), unlike the copy and
# the verify which were disk-bound - so workers genuinely help here. Measured
# 0.23 s an image and 1.67 s a video single-threaded: ~8 h for 81,364 assets,
# roughly 2 h across six shards.
$log = 'D:\_PhotoAudit\thumbs-chain.log'
# Add-Content + Write-Host, never Tee-Object: Tee writes the line to the OUTPUT
# stream too, so a Say inside an Invoke-Step gate lands in that gate's return
# value and a non-empty array is $true. See chain_mirror_h.ps1 for the night
# that cost.
function Say($m) {
    $line = "$((Get-Date).ToString('HH:mm:ss'))  $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}

Say 'waiting for the H: ingest to finish'
while ($true) {
    $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
         Where-Object { $_.CommandLine -match 'ingest_from_h|ingest_tree' }
    if (-not $p) { break }
    Start-Sleep -Seconds 60
}
Say 'ingest process gone'

if (Select-String -Path D:\_PhotoAudit\h-ingest-all.log -Pattern 'HALT:' -Quiet) {
    Say 'NOTE: the ingest log contains a HALT line. Check whether it halted on'
    Say 'the space floor before finishing from-wd6400. Thumbnails still proceed;'
    Say 'they only cover what is on disk, and a later ingest can be thumbnailed again.'
}

$fail = Join-Path $env:TEMP 'H-COPY-FAILURES.csv'
if (Test-Path 'D:\_PhotoAudit\H-COPY-FAILURES.csv') {
    $n = (Get-Content 'D:\_PhotoAudit\H-COPY-FAILURES.csv' | Measure-Object -Line).Lines
    Say "WARNING: H-COPY-FAILURES.csv exists with $n lines - files that never reached the library."
} else {
    Say 'H-COPY-FAILURES.csv absent: nothing failed to copy off H:'
}

$env:PYTHONIOENCODING = 'utf-8'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$eng = "$repo\stages\05_enrich\thumbnail.py"
. "$PSScriptRoot\steps.ps1"
# A supervisor that failed to load is indistinguishable from one that approved
# everything, because PowerShell reports an unknown command and carries on.
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load - nothing could be supervised.'
    exit 1
}

# Stop-Chain is what Invoke-Step calls on a failed guard; this chain had no such
# concept, so give it one rather than let the runner throw an unhandled error.
function Stop-Chain([string] $why) { Say "STOPPED: $why"; exit 1 }
function Count-Thumbs {
    (Get-ChildItem D:\_thumbs -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
}

Invoke-Step -Name 'thumbnails' -ExpectedUnits 97000 -CheckpointMin 15 `
    -Preflight {
        if (-not (Test-Path 'D:\ContentLibrary\Media')) { Say '  no source tree'; return $false }
        # Make ONE thumbnail before starting six shards over a whole library.
        # thumbnail.py silently produced landscape thumbnails from portrait
        # originals for weeks because nothing ever looked at one it made.
        $probe = & python -c "import importlib.util,sys;spec=importlib.util.spec_from_file_location('t',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);print('OK' if callable(getattr(m,'make',None)) else 'NO')" $eng 2>&1 | Select-Object -Last 1
        if ("$probe" -ne 'OK') { Say "  thumbnail.make unavailable ('$probe')"; return $false }
        return $true
    } `
    -Start {
        Say 'starting 6 thumbnail shards over D:\ContentLibrary\Media'
        $jobs = @()
        foreach ($i in 0..5) {
            $jobs += Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
                '-u', $eng,
                '--source', 'D:\ContentLibrary\Media',
                '--out', 'D:\_thumbs',
                '--shard', "$i/6"
            ) -RedirectStandardOutput "D:\_PhotoAudit\thumbs-$i.log" -RedirectStandardError "D:\_PhotoAudit\thumbs-$i.err"
        }
        Say ("shards running: " + ($jobs.Id -join ', '))
        return $jobs
    } `
    -Progress { Count-Thumbs } `
    -Verify {
        # A thumbnail count proves files appeared, not that they are pictures.
        # thumbnail.py spent weeks writing landscape thumbnails of portrait
        # photographs and the count was perfect throughout. So open a few of the
        # newest and check they decode, have sensible dimensions, and are not
        # uniformly blank.
        $chk = & python -c @"
import glob, os, sys
import numpy as np
from PIL import Image
files = sorted(glob.glob(r'D:\_thumbs\**\*.jpg', recursive=True),
               key=os.path.getmtime)[-6:]
if len(files) < 3:
    print('too few thumbnails yet'); sys.exit(2)
bad = 0
for p in files:
    try:
        im = Image.open(p); im.load()
        w, h = im.size
        a = np.asarray(im.convert('L'), dtype=np.float32)
        if max(w, h) < 64 or max(w, h) > 4096 or a.std() < 1.0:
            bad += 1; print('  {} {}x{} std {:.1f}'.format(os.path.basename(p)[:20], w, h, a.std()))
    except Exception as e:
        bad += 1; print('  {} will not open: {}'.format(os.path.basename(p)[:20], e))
print('checked {} newest thumbnails, {} unusable'.format(len(files), bad))
sys.exit(1 if bad else 0)
"@ 2>&1 | Out-String
        foreach ($ln in ($chk -split "`n" | Where-Object { $_.Trim() })) { Say "    $ln" }
        return ($LASTEXITCODE -ne 1)
    } `
    -Postcondition {
        $n = Count-Thumbs
        Say "  thumbnails on disk: $n"
        return ($n -gt 0)
    }
Say 'all shards finished'

$n = Count-Thumbs
Say "thumbnails on disk: $n"
Say 'DONE. Next: stages/05_enrich/classify_live.py --thumbs D:\_thumbs --store D:\_enrichment --apply'
