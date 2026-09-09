r"""Sample several frames from a video, so a judgement about it is not made on
one instant.

WHY

A ten-minute clip has one thumbnail. Asking "is there anything sensitive in
this video?" of a single frame is not a cheap answer, it is a meaningless one -
the frame is 0.2% of the content and was chosen for being early, not for being
representative.

But sampling evenly is also wrong for this corpus. The long videos here are
unedited footage - podcast recordings, scuba dives - which open with lens caps,
setup and dead air. The informative part starts minutes in.

THE POLICY (set by the library's owner)

    < 30 s        2 frames   25%, 65%
    30 s - 3 min  3 frames   20%, 50%, 80%
    3 - 15 min    4 frames   first at 3:00, then spread to 90%
    > 15 min      5 frames   first at 3:00, then spread to 90%   <- hard cap

The cap is the point: a 90-minute podcast costs exactly what a 16-minute one
does. Without it, cost scales with the least interesting content in the
library.

Frames are written beside the existing thumbnail and keyed by the same content
hash:

    <out>/<hash[:2]>/<hash>.jpg        the existing single thumbnail (unchanged)
    <out>/<hash[:2]>/<hash>_f0.jpg     sampled frames
    <out>/<hash[:2]>/<hash>_f1.jpg

    python frames.py --root D:\ContentLibrary --out D:\_thumbs
    python frames.py --root ... --out ... --shard 0/6
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thumbnail import VIDEO, FFMPEG, lp                          # noqa: E402
from store import content_hash                                   # noqa: E402

FFPROBE = os.environ.get("FFPROBE_PATH") or "ffprobe"
MAX_FRAMES = 5


def duration_s(src: str) -> float | None:
    """Seconds, or None if ffprobe cannot say. None means 'do not guess'."""
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", src],
            capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout or "{}").get("format", {}).get("duration")
        return float(d) if d else None
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


def offsets(dur: float) -> list[float]:
    """Seconds into the clip to sample, per the policy above."""
    if dur < 30:
        return [dur * 0.25, dur * 0.65]
    if dur < 180:
        return [dur * 0.20, dur * 0.50, dur * 0.80]

    n = 4 if dur < 900 else MAX_FRAMES
    start = min(180.0, dur * 0.10)      # 3:00 in, unless the clip is short
    end = dur * 0.90                     # never the final frames: fades, black
    if end <= start:
        return [dur * 0.5]
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


def grab(src: str, at: float, dst: str, size: int) -> bool:
    try:
        r = subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", src,
             "-frames:v", "1",
             "-vf", f"scale='min({size},iw)':-2", "-q:v", "4", dst],
            capture_output=True, timeout=180)
        return r.returncode == 0 and os.path.exists(dst) \
            and os.path.getsize(dst) > 0
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--shard", default="")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    si = sn = 0
    if a.shard:
        si, sn = (int(x) for x in a.shard.split("/"))

    vids = []
    for dp, dns, fns in os.walk(a.root):
        for fn in fns:
            if os.path.splitext(fn)[1].lower() not in VIDEO:
                continue
            p = os.path.join(dp, fn)
            if sn and (zlib.crc32(p.lower().encode()) % sn) != si:
                continue
            vids.append(p)
    print(f"videos: {len(vids):,}" + (f"  shard {si}/{sn}" if sn else ""))
    if a.limit:
        vids = vids[:a.limit]

    made = skipped = failed = noduration = 0
    for i, p in enumerate(vids, 1):
        try:
            h = content_hash(p)
        except OSError:
            failed += 1
            continue
        sub = os.path.join(a.out, h[:2])
        os.makedirs(lp(sub), exist_ok=True)
        if os.path.exists(os.path.join(sub, h + "_f0.jpg")):
            skipped += 1
            continue

        dur = duration_s(p)
        if dur is None or dur <= 0:
            # No duration means no basis for choosing offsets. Fall back to the
            # single existing thumbnail rather than inventing timestamps.
            noduration += 1
            continue

        got = 0
        for k, at in enumerate(offsets(dur)):
            if grab(p, at, os.path.join(sub, f"{h}_f{k}.jpg"), a.size):
                got += 1
        if got:
            made += 1
        else:
            failed += 1

        if i % 100 == 0:
            print(f"  {i:,}/{len(vids):,}  made={made} skipped={skipped} "
                  f"failed={failed} no-duration={noduration}", flush=True)

    print(f"\nframe sets made {made:,}, already present {skipped:,}, "
          f"failed {failed:,}, no duration {noduration:,}")


if __name__ == "__main__":
    main()
