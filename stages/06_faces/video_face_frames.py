r"""Sample frames from every video for face detection, densely enough that a long
home video is not judged on five instants.

    python video_face_frames.py --out D:\_frames                  # every video
    python video_face_frames.py --out D:\_frames --shard 0/3
    python video_face_frames.py --out D:\_frames --limit 20       # a probe
    python video_face_frames.py --out D:\_frames --outstanding    # what is left NOW
    python video_face_frames.py --out D:\_frames --verify 6       # 0 right, 1 wrong, 2 nothing yet

WHY NOT frames.py

frames.py samples 2-5 frames per video for the CLASSIFIER, and caps at five on
purpose: every frame there is paid for. For faces the cost is local CPU, and a
cap of five misses nearly everyone in a forty-minute birthday - and nearly
everyone on a two-hour digitised VHS tape, which is where the Communal side is
headed. Krish asked on 2026-09-15 for every video to be tagged with faces.

THE POLICY

    < 30 s     2 frames, at 25% and 65%
    otherwise  one per STEP seconds, at least 2, at most MAX_FRAMES, each centred
               in its slice so neither the first nor the last second is used

Measured on this library the same day: 12,805 videos, 136 hours, 32,670 frames,
about 18 hours of face detection at the measured 0.5 images/s.

A separate tree, not beside the thumbnails, because batch_classify.assets_for
treats <hash>_fN.jpg in D:\_thumbs as frames to SEND TO THE MODEL, and sixty of
them per video would multiply the next classification bill:

    <out>/<hash[:2]>/<hash>_t<milliseconds>.jpg     a frame
    <out>/<hash[:2]>/<hash>_t<milliseconds>.failed  ffmpeg could not grab it

Milliseconds, not seconds. The probe named frames by whole seconds, and a clip
shorter than two seconds put both of its frames at _t0 - the second overwrote the
first and the run still reported two frames made (learning 23).

A frame ffmpeg cannot grab gets a .failed marker saying why, so a resumed run does
not retry it for ever and --outstanding can tell "not done yet" from "cannot be
done" - the difference between a postcondition that can pass and one that never
will (learning 47).

Hashes come from library.db, which holds one for every file. frames.py hashes
each video itself; doing that here would re-read 136 hours of footage to learn
something already known. A video library.db lists but the disk does not have is
COUNTED and reported, and too many of them stops the run: an absent input is not
an empty one (learnings 34, 41).
"""

from __future__ import annotations

import argparse
import io
import math
import os
import random
import re
import sqlite3
import sys
import tempfile
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path

# frames.py lives in 05 enrich; stagepath is what makes this resolve, so it must
# be imported above this line and not below it.
from frames import duration_s, grab                              # noqa: E402

DB = r"D:\_PhotoAudit\library.db"
STEP = 30.0
MAX_FRAMES = 60
FRAME = re.compile(r"^([0-9a-f]{64})_t(\d+)\.jpg$")


def offsets(dur: float) -> list[float]:
    """Seconds into the clip to sample, per the policy above."""
    if dur < 30:
        return [dur * 0.25, dur * 0.65]
    n = min(MAX_FRAMES, max(2, math.ceil(dur / STEP)))
    return [dur * (i + 0.5) / n for i in range(n)]


def targets(out: str, h: str, dur: float) -> list[tuple[float, str]]:
    """-> [(seconds, frame path)], every path distinct.

    Two offsets can round to the same millisecond only on a clip a few
    milliseconds long; they name the same frame, so it is sampled once rather
    than written twice to one path."""
    sub = os.path.join(out, h[:2])
    seen, res = set(), []
    for t in offsets(dur):
        dst = os.path.join(sub, "{}_t{}.jpg".format(h, int(round(t * 1000))))
        if dst not in seen:
            seen.add(dst)
            res.append((t, dst))
    return res


def marker(dst: str) -> str:
    return dst[:-4] + ".failed"


def videos(db_path: str) -> tuple[list[tuple[str, str, float | None]], int]:
    """-> ([(hash, path, duration)], videos with no path on disk).

    One row per distinct video, first path that exists. A hash can sit at several
    paths (hardlinks, duplicates) and its frames are the same whichever is read."""
    if not os.path.exists(db_path):
        raise SystemExit("STOPPING: no library.db at {}".format(db_path))
    db = sqlite3.connect("file:{}?mode=ro".format(db_path.replace("\\", "/")),
                         uri=True)
    try:
        rows = db.execute(
            "SELECT hash, path, duration FROM files "
            "WHERE media = 'video' AND hash IS NOT NULL ORDER BY hash, path").fetchall()
    finally:
        db.close()          # never hold the database open: build_db renames over it
    found, known = {}, set()
    for h, p, d in rows:
        known.add(h)
        if h not in found and os.path.exists(p):
            found[h] = (h, p, d)
    return list(found.values()), len(known) - len(found)


def verify(a) -> int:
    """Re-grab a sample of finished frames from their source video and compare.

    Not "is it a jpg": a frame written under the wrong hash is a perfectly good
    jpg of somebody else's video, and every face found in it would be attached
    to the wrong file. Only re-deriving the frame from the path library.db gives
    for that hash can tell."""
    import numpy as np
    from PIL import Image

    found = []
    if os.path.isdir(a.out):
        for sub in os.listdir(a.out):
            d = os.path.join(a.out, sub)
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    m = FRAME.match(fn)
                    if m:
                        found.append((m.group(1), int(m.group(2)),
                                      os.path.join(d, fn)))
    if not found:
        print("verify: no frames yet")
        return 2
    pick = random.Random(len(found)).sample(found, min(a.verify, len(found)))
    src = {h: p for h, p, _ in videos(a.db)[0]}

    bad = checked = 0
    for h, ms, fp in pick:
        if os.path.getsize(fp) == 0:                 # never valid content (learning 6)
            bad += 1
            print("  {}_t{}  zero bytes".format(h[:12], ms))
            continue
        p = src.get(h)
        if not p:
            bad += 1
            print("  {}  frame for a hash with no video on disk".format(h[:12]))
            continue
        tmp = os.path.join(tempfile.gettempdir(),
                           "vff-verify-{}-{}.jpg".format(h[:12], ms))
        if not grab(p, ms / 1000.0, tmp, a.size):
            continue
        try:
            x = np.asarray(Image.open(fp).convert("L").resize((64, 64)), dtype=np.float32)
            y = np.asarray(Image.open(tmp).convert("L").resize((64, 64)), dtype=np.float32)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        diff = float(np.abs(x - y).mean())
        checked += 1
        if diff > 8.0:
            bad += 1
            print("  {}_t{}  mean pixel difference {:.1f}  MISMATCH".format(
                h[:12], ms, diff))
    if checked == 0 and not bad:
        # frames exist and none could be re-derived: not "can't tell" (learning 6)
        print("verify: could not re-grab ANY of {} sampled frames".format(len(pick)))
        return 1
    print("verify: re-grabbed {} of {:,} frames, {} wrong".format(
        checked, len(found), bad))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--shard", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verify", type=int, default=0,
                    help="re-derive this many finished frames and exit")
    ap.add_argument("--outstanding", action="store_true",
                    help="count what is left to do now, from disk, and exit")
    ap.add_argument("--max-missing", type=float, default=0.02,
                    help="stop if more than this share of videos is not on disk")
    a = ap.parse_args()

    if a.verify:
        return verify(a)

    vids, missing = videos(a.db)
    total = len(vids) + missing
    print("videos in library.db: {:,}   on disk: {:,}   missing from disk: {:,}".format(
        total, len(vids), missing), flush=True)
    if total == 0:
        print("STOPPING: library.db lists no videos - that is a broken query or "
              "the wrong database, not an empty library (learning 34)")
        return 1
    if missing > max(20, total * a.max_missing):
        print("STOPPING: {:,} of {:,} videos are not on disk. A drive letter moved "
              "or the library was reorganised after library.db was built. Rebuild "
              "it, or pass --max-missing deliberately.".format(missing, total))
        return 1

    if a.outstanding:
        todo = present = failed = nodur = 0
        for h, p, d in vids:
            if not d or d <= 0:
                d = duration_s(p)
            if not d or d <= 0:
                nodur += 1
                continue
            for _, dst in targets(a.out, h, d):
                if os.path.exists(dst):
                    present += 1
                elif os.path.exists(marker(dst)):
                    failed += 1
                else:
                    todo += 1
        print("frames outstanding: {:,}  present: {:,}  failed: {:,}  "
              "videos without duration: {:,}  videos missing from disk: {:,}".format(
                  todo, present, failed, nodur, missing))
        return 0

    si = sn = 0
    if a.shard:
        si, sn = (int(x) for x in a.shard.split("/"))
    if sn:
        vids = [v for v in vids if zlib.crc32(v[0].encode()) % sn == si]
    if a.limit:
        vids = vids[:a.limit]
    planned = sum(len(targets(a.out, h, d)) for h, _, d in vids if d)
    print("videos this run: {:,}{}   frames planned: {:,}".format(
        len(vids), "  shard {}/{}".format(si, sn) if sn else "", planned),
        flush=True)

    made = present = failed = noduration = 0
    t0 = time.time()
    for i, (h, p, d) in enumerate(vids, 1):
        if not d or d <= 0:
            d = duration_s(p)
        if not d or d <= 0:
            # no duration, no basis for offsets: the existing thumbnail stands
            noduration += 1
            continue
        want = targets(a.out, h, d)
        todo = [(t, dst) for t, dst in want
                if not os.path.exists(dst) and not os.path.exists(marker(dst))]
        present += len(want) - len(todo)
        if todo:
            os.makedirs(os.path.dirname(todo[0][1]), exist_ok=True)
        for t, dst in todo:
            # written under a temporary name and renamed, so a kill mid-write
            # never leaves a truncated jpg that resume would count as done
            tmp = dst[:-4] + ".tmp.jpg"
            if grab(p, t, tmp, a.size):
                os.replace(tmp, dst)
                made += 1
            else:
                failed += 1
                if os.path.exists(tmp):
                    os.remove(tmp)
                with io.open(marker(dst), "w", encoding="utf-8") as f:
                    f.write("ffmpeg could not grab t={:.3f}s from {}\n".format(t, p))
        if i % 100 == 0:
            print("  {:,}/{:,} videos  made={:,} present={:,} failed={:,} "
                  "no-duration={:,}  {:.0f} min".format(
                      i, len(vids), made, present, failed, noduration,
                      (time.time() - t0) / 60), flush=True)

    print("\nframes made {:,}, already present {:,}, failed {:,}, "
          "videos with no duration {:,}, {:.0f} min".format(
              made, present, failed, noduration, (time.time() - t0) / 60))
    print("finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
