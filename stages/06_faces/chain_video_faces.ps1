# Faces for every video, not only its thumbnail.
#
# Krish, 2026-09-15: "All videos should be tagged with faces too." Measured the
# same day: detection had seen one frame per video, 10% in, and only for videos
# the classifier said had people in them - 4,237 of 12,805 videos had a face.
#
#   frames   video_face_frames.py   one frame per 30 s, 2-60 a video, D:\_frames
#   faces    faces_embed.py --frames, ONE process: one is fastest here (11629a4)
#   assign   assign_video_faces.py  joins the frozen clusters and never
#            renumbers them, because Krish's answers point at cluster ids
#   rebuild  build_db.py, so the people he has named appear on the videos
#
# Safe to re-run. Frames and faces resume; assign refuses to tag twice, so a
# restart after it has applied skips it rather than failing on the refusal.
#
#   pwsh -NoProfile -File guards\arm.ps1 -Chain chain_video_faces.ps1
param([int] $FrameShards = 3)

$log  = 'D:\_PhotoAudit\video-faces.log'
$repo = 'C:\Users\krish\dev\contentarchives'
function Say($m) {
    $line = "$((Get-Date).ToString('HH:mm:ss'))  $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}

$halt = 'D:\_PhotoAudit\VIDEO-FACES-HALTED.txt'
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
. "$PSScriptRoot\steps.ps1"
if (-not (Get-Command Invoke-Step -ErrorAction SilentlyContinue)) {
    Say 'STOPPED: steps.ps1 did not load - nothing could be supervised.'
    exit 1
}

$frames = 'D:\_frames'
$vcsv   = 'D:\_enrichment\faces.video.csv'
$tags   = 'D:\_enrichment\content_tags.csv'

function Count-Frames {
    if (-not (Test-Path $frames)) { return 0 }
    (Get-ChildItem -Path $frames -Recurse -File -Filter '*.jpg' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike '*.tmp.jpg' } | Measure-Object).Count
}

# Opened with ReadWrite sharing: faces_embed.py has the file open for append,
# and File.ReadLines asks for exclusive-write sharing and throws against it.
function Count-Lines([string] $p) {
    if (-not (Test-Path $p)) { return 0 }
    $fs = [System.IO.FileStream]::new($p, 'Open', 'Read', 'ReadWrite')
    $sr = [System.IO.StreamReader]::new($fs)
    $n = 0
    try { while ($null -ne $sr.ReadLine()) { $n++ } } finally { $sr.Dispose() }
    return $n
}

Say '=== video faces start (safe to restart; every step resumes) ==='

# ---- 1. frames ---------------------------------------------------------------
Invoke-Step -Name 'frames' -ExpectedUnits 32670 -CheckpointMin 15 -VerifyEvery 4 -StallStrikes 3 `
    -Preflight {
        # three videos end to end, then re-derive what was written from source
        python -u "$repo\stages\06_faces\video_face_frames.py" --out $frames --limit 3 *>> $log
        if ($LASTEXITCODE -ne 0) { return $false }
        if ((Count-Frames) -lt 1) { Say '  the probe wrote no frames'; return $false }
        python -u "$repo\stages\06_faces\video_face_frames.py" --out $frames --verify 4 *>> $log
        if ($LASTEXITCODE -ne 0) { return $false }
        # Exercise the postcondition's own question now, so a check that could
        # never parse its answer is found in minutes, not after ten hours (47).
        $o = & python "$repo\stages\06_faces\video_face_frames.py" --out $frames --outstanding 2>&1 | Out-String
        Add-Content -Path $log -Value $o.Trim()
        return ($o -match 'frames outstanding: [\d,]+\s+present: [\d,]+\s+failed: [\d,]+')
    } `
    -Start {
        Get-ChildItem 'D:\_PhotoAudit\video-frames-*.out' -ErrorAction SilentlyContinue | Remove-Item
        foreach ($i in 0..($FrameShards - 1)) {
            Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
                '-u', "$repo\stages\06_faces\video_face_frames.py", '--out', $frames,
                '--shard', "$i/$FrameShards"
            ) -RedirectStandardOutput "D:\_PhotoAudit\video-frames-$i.out" `
              -RedirectStandardError  "D:\_PhotoAudit\video-frames-$i.err"
        }
    } `
    -Progress { Count-Frames } `
    -Verify {
        python -u "$repo\stages\06_faces\video_face_frames.py" --out $frames --verify 6 *>> $log
        return ($LASTEXITCODE -ne 1)
    } `
    -Postcondition {
        # Ask the disk what is left NOW (learning 47), not what the shard logs
        # announced. A frame ffmpeg could not grab carries a .failed marker, so
        # "outstanding" can reach zero on a library with a few broken clips, and
        # the broken ones are counted rather than hidden.
        $o = & python "$repo\stages\06_faces\video_face_frames.py" --out $frames --outstanding 2>&1 | Out-String
        Add-Content -Path $log -Value $o.Trim()
        $m = [regex]::Match($o, 'frames outstanding: ([\d,]+)\s+present: ([\d,]+)\s+failed: ([\d,]+)')
        if (-not $m.Success) { Say '  could not read the outstanding count'; return $false }
        $left    = [int]($m.Groups[1].Value -replace ',', '')
        $present = [int]($m.Groups[2].Value -replace ',', '')
        $failed  = [int]($m.Groups[3].Value -replace ',', '')
        Say ("  frames present {0:N0}, outstanding {1:N0}, could not be grabbed {2:N0}" -f $present, $left, $failed)
        if ($left -ne 0) { return $false }
        if ($present -lt 25000) { Say '  far fewer frames than the ~32,670 planned'; return $false }
        return ($failed -le [math]::Max(50, ($present + $failed) * 0.02))
    }

# ---- 2. faces ----------------------------------------------------------------
# ExpectedUnits is LINES in faces.video.csv, the unit -Progress counts: one per
# face found, or one for a frame with none. ~32,670 frames at an unmeasured
# faces-per-frame; the checkpoint will recalibrate out loud.
Invoke-Step -Name 'faces' -ExpectedUnits 45000 -CheckpointMin 15 -VerifyEvery 4 -StallStrikes 3 `
    -Preflight {
        python -u "$repo\stages\06_faces\faces_embed.py" --frames $frames --store D:\_enrichment --limit 3 *>> $log
        if ($LASTEXITCODE -ne 0) { return $false }
        if ((Count-Lines $vcsv) -lt 2) { Say '  the probe wrote no rows'; return $false }
        python -u "$repo\stages\06_faces\verify_faces.py" --csv $vcsv --sample 4 *>> $log
        if ($LASTEXITCODE -eq 1) { return $false }
        # the postcondition's own question, exercised now (learning 47)
        $o = & python "$repo\stages\06_faces\faces_embed.py" --frames $frames --store D:\_enrichment --dry-run 2>&1 | Out-String
        Add-Content -Path $log -Value $o.Trim()
        return ($o -match '[\d,]+ images to look at, [\d,]+ already done, [\d,]+ unreadable')
    } `
    -Start {
        Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
            '-u', "$repo\stages\06_faces\faces_embed.py", '--frames', $frames,
            '--store', 'D:\_enrichment'
        ) -RedirectStandardOutput 'D:\_PhotoAudit\video-faces.out' `
          -RedirectStandardError  'D:\_PhotoAudit\video-faces.err'
    } `
    -Progress { Count-Lines $vcsv } `
    -Verify {
        python -u "$repo\stages\06_faces\verify_faces.py" --csv $vcsv --sample 8 *>> $log
        return ($LASTEXITCODE -ne 1)
    } `
    -Postcondition {
        # Ask whether any frame is still unexamined NOW. --dry-run is essential:
        # without it this check would START the remaining detection inside the
        # postcondition, unsupervised, whenever anything was left (learning 47).
        $o = & python "$repo\stages\06_faces\faces_embed.py" --frames $frames --store D:\_enrichment --dry-run 2>&1 | Out-String
        Add-Content -Path $log -Value $o.Trim()
        $m = [regex]::Match($o, '([\d,]+) images to look at, ([\d,]+) already done, ([\d,]+) unreadable')
        if (-not $m.Success) { Say '  could not read the outstanding count'; return $false }
        $left = [int]($m.Groups[1].Value -replace ',', '')
        $done = [int]($m.Groups[2].Value -replace ',', '')
        $bad  = [int]($m.Groups[3].Value -replace ',', '')
        Say ("  frames examined {0:N0}, not yet {1:N0}, unreadable {2:N0}" -f $done, $left, $bad)
        if ($left -ne 0) { return $false }
        return ($bad -le [math]::Max(20, $done * 0.005))
    }

# ---- 3. assign ---------------------------------------------------------------
if (Select-String -Path $tags -Pattern ',faces-video,' -SimpleMatch -Quiet -ErrorAction SilentlyContinue) {
    Say '[assign] already applied (faces-video tags are in the store) - skipping'
} else {
    Invoke-Step -Name 'assign' -CheckpointMin 10 -VerifyEvery 1 -StallStrikes 6 `
        -Preflight {
            # the dry run reads everything the real run reads and writes nothing
            python -u "$repo\stages\06_faces\assign_video_faces.py" *>> $log
            return ($LASTEXITCODE -eq 0)
        } `
        -Start {
            Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
                '-u', "$repo\stages\06_faces\assign_video_faces.py", '--apply'
            ) -RedirectStandardOutput 'D:\_PhotoAudit\video-assign.out' `
              -RedirectStandardError  'D:\_PhotoAudit\video-assign.err'
        } `
        -Progress { [double]((Get-Item 'D:\_PhotoAudit\video-assign.out' -ErrorAction SilentlyContinue).Length) } `
        -Verify {
            python -u "$repo\stages\06_faces\assign_video_faces.py" --verify *>> $log
            return ($LASTEXITCODE -ne 1)
        } `
        -Postcondition {
            Get-Content 'D:\_PhotoAudit\video-assign.out' -ErrorAction SilentlyContinue | Add-Content -Path $log
            $o = Get-Content 'D:\_PhotoAudit\video-assign.out' -Raw -ErrorAction SilentlyContinue
            if ($o -notmatch 'cluster tags \(source faces-video\)') { return $false }
            python -u "$repo\stages\06_faces\assign_video_faces.py" --verify *>> $log
            return ($LASTEXITCODE -eq 0)
        }
}

# ---- 4. rebuild --------------------------------------------------------------
Invoke-Step -Name 'rebuild' -CheckpointMin 5 -VerifyEvery 1 -StallStrikes 4 `
    -Preflight {
        python -u "$repo\tests\test_build_db.py" *>> $log
        return ($LASTEXITCODE -eq 0)
    } `
    -Start {
        Start-Process python -PassThru -WindowStyle Hidden -ArgumentList @(
            '-u', "$repo\stages\08_index\build_db.py"
        ) -RedirectStandardOutput 'D:\_PhotoAudit\video-rebuild.out' `
          -RedirectStandardError  'D:\_PhotoAudit\video-rebuild.err'
    } `
    -Progress { [double]((Get-ChildItem 'D:\_PhotoAudit\library.db*' -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum) } `
    -Verify {
        # While the build runs, library.db is still the previous one and cannot
        # say anything about this run; the check that means something is the
        # postcondition, against the database that replaced it.
        if (Test-Path 'D:\_PhotoAudit\library.db.tmp') { return $true }
        python -u "$repo\stages\06_faces\assign_video_faces.py" --verify-db *>> $log
        return ($LASTEXITCODE -ne 1)
    } `
    -Postcondition {
        $o = Get-Content 'D:\_PhotoAudit\video-rebuild.out' -Raw -ErrorAction SilentlyContinue
        if ($o -notmatch 'wrote .*library\.db') { return $false }
        python -u "$repo\stages\06_faces\assign_video_faces.py" --verify-db *>> $log
        return ($LASTEXITCODE -eq 0)
    }

Say 'VIDEO FACES COMPLETE. Regenerate PEOPLE.html: video-only people now have rows.'
