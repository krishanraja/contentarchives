r"""Thumbnail the files the thumbnailer was never pointed at.

WHY THIS EXISTS

chain_thumbnails.ps1 ran `thumbnail.py --source D:\ContentLibrary\Media`. Three
trees are not under Media\: `Archive\`, `_Review\` and `ContentProduction\`. So
2,706 files with perfectly supported extensions have no thumbnail and no frames,
which means no classifier, no face pass and no game has ever seen them. They are
not unclassified because they are hard; they are unclassified because nothing
ever looked.

That was found while answering a much sharper question - "are you sure every
intimate photograph is in the Intimate folder?" - and the answer could only be
no while 1,750 photographs and 956 videos were invisible. Recall cannot be
claimed over files nobody has looked at.

WHY NOT JUST RE-RUN thumbnail.py OVER A BIGGER --source

`make()` calls content_hash(src) BEFORE checking whether the thumbnail already
exists, so pointing it at the whole library re-reads ~82,000 files to discover
that 79,000 of them are already done. One of those files is a 108 GB .jpg
(D:\ContentLibrary\Media\Personal\NoDate\1000002434.jpg - almost certainly a
disk image, not a photograph), which alone would be read end to end for nothing.

So this drives from the index instead: library.db already holds path -> hash for
every file, and those hashes were verified to match content_hash exactly
(14/14 on a spread of extensions, 2026-09-17). Nothing is re-hashed, nothing is
re-read, and the thumbnail still lands under the content-addressed name that
assets_for() looks for.

WHAT COUNTS AS A FAILURE

Not every one of these is a photograph. The gap contains 0-byte PNGs, AppleDouble
resource forks (`._name.jpg`), 3 KB truncated WhatsApp stubs, and `AUD-*.3gp`
files which are AUDIO in a video container - no frame exists to extract. ffmpeg
refusing those is correct. So every outcome is written to a log with a reason,
because "2,706 attempted, 2,400 made" is not a finding until you can say what the
other 306 were.

    python backfill_thumbs.py --out D:\_thumbs --media photo
    python backfill_thumbs.py --out D:\_thumbs --media video --shard 0/4
    python backfill_thumbs.py --out D:\_thumbs --dry-run
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import os
import sqlite3
import sys
import zlib

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path

import paths as P                                                 # noqa: E402
import thumbnail as T                                             # noqa: E402
import frames as F                                                # noqa: E402
from batch_classify import assets_for                             # noqa: E402

LOG = "thumb-backfill.csv"
LOG_COLS = ["when", "hash", "ext", "bytes", "outcome", "detail", "path"]

# No photograph is half a gigabyte. A .jpg above this is a container, a disk
# image or a corruption, and handing it to Pillow costs minutes and a lot of
# memory to learn that. Videos have no such cap: ffmpeg seeks, it does not read.
MAX_PHOTO_BYTES = 512 * 1024 * 1024


def gap(dbpath: str, out: str, media: str) -> tuple[list[tuple], int]:
    """(path, hash, ext, bytes) for every file no classifier can see.

    Deduplicated by hash: the thumbnail is content-addressed, so two paths
    holding the same bytes are one piece of work, not two.
    """
    db = sqlite3.connect("file:{}?mode=ro".format(dbpath.replace("\\", "/")),
                         uri=True)
    try:
        rows = db.execute("select path, hash, bytes from files").fetchall()
    finally:
        db.close()

    assets = assets_for(out)
    seen: set[str] = set()
    todo: list[tuple] = []
    dupes = 0
    for path, h, nbytes in rows:
        if not h or h in assets:
            continue
        ext = os.path.splitext(path or "")[1].lower()
        if ext in T.PHOTO:
            kind = "photo"
        elif ext in T.VIDEO:
            kind = "video"
        else:
            continue                      # documents, audio, archives: not ours
        if media != "both" and kind != media:
            continue
        if h in seen:
            dupes += 1
            continue
        seen.add(h)
        todo.append((path, h, ext, nbytes or 0, kind))
    return todo, dupes


def one(path: str, h: str, ext: str, nbytes: int, kind: str,
        out: str, size: int, video_mode: str,
        max_photo_bytes: int) -> tuple[str, str]:
    """Make the thumbnail. Returns (outcome, detail). Never raises."""
    sub = os.path.join(out, h[:2])
    try:
        os.makedirs(T.lp(sub), exist_ok=True)
    except OSError as e:
        return "failed", "mkdir: {}".format(e)

    single = os.path.join(sub, h + ".jpg")
    frame0 = os.path.join(sub, h + "_f0.jpg")

    if kind == "photo":
        if os.path.exists(single) and os.path.getsize(single) > 0:
            return "already", ""
        if nbytes <= 0:
            return "skipped", "zero bytes on disk"
        if nbytes > max_photo_bytes:
            return "skipped", "{:.1f} GB is not a photograph".format(
                nbytes / 1073741824.0)
        if os.path.basename(path).startswith("._"):
            return "skipped", "AppleDouble resource fork, not an image"
        if T._pillow(path, single, size) or T._ffmpeg_image(path, single, size):
            return "made", ""
        return "failed", "no decoder could open it"

    # video
    if video_mode == "frames":
        if os.path.exists(frame0) and os.path.getsize(frame0) > 0:
            return "already", ""
        dur = F.duration_s(path)
        if dur and dur > 0:
            got = 0
            for k, at in enumerate(F.offsets(dur)):
                if F.grab(path, at, os.path.join(sub, "{}_f{}.jpg".format(h, k)),
                          size):
                    got += 1
            if got:
                return "made", "{} frames of {:.0f}s".format(got, dur)
        # No duration, or every grab failed. A single thumbnail is worth more
        # than nothing for a triage pass, so fall back rather than give up.
        if os.path.exists(single) and os.path.getsize(single) > 0:
            return "already", "single thumbnail only"
        if T._ffmpeg_video(path, single, size):
            return "made", "single frame only (no duration)" if not dur \
                else "single frame only (frame grabs failed)"
        return "failed", "no duration and no extractable frame" if not dur \
            else "duration known but no frame could be extracted"

    if os.path.exists(single) and os.path.getsize(single) > 0:
        return "already", ""
    if T._ffmpeg_video(path, single, size):
        return "made", ""
    return "failed", "no frame could be extracted"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"),
                    help="the index holding path -> hash")
    ap.add_argument("--out", default=r"D:\_thumbs", help="thumbnail cache")
    ap.add_argument("--media", choices=("photo", "video", "both"), default="both")
    ap.add_argument("--video-mode", choices=("frames", "single"), default="frames",
                    help="frames: 2-5 across the clip, per frames.py's policy. "
                         "A single 10%% thumbnail is what makes a judgement "
                         "about a video meaningless.")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--shard", default="", help="i/n - split by a hash of the path")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-photo-bytes", type=int, default=MAX_PHOTO_BYTES)
    ap.add_argument("--log", default="",
                    help="outcome log (default: " + os.path.join(P.AUDIT, LOG) + ")")
    ap.add_argument("--dry-run", action="store_true",
                    help="say what would be attempted; make nothing")
    a = ap.parse_args()

    si = sn = 0
    if a.shard:
        si, sn = (int(x) for x in a.shard.split("/"))

    todo, dupes = gap(a.db, a.out, a.media)
    if sn:
        todo = [t for t in todo
                if (zlib.crc32(t[0].lower().encode()) % sn) == si]
    print("files a classifier cannot see: {:,}{}".format(
        len(todo), "  shard {}/{}".format(si, sn) if sn else ""))
    print("  duplicate hashes collapsed: {:,}".format(dupes))
    by = collections.Counter(k for _, _, _, _, k in todo)
    print("  photo {:,}   video {:,}".format(by["photo"], by["video"]))
    if a.limit:
        todo = todo[:a.limit]
        print("  limited to {:,}".format(len(todo)))

    if a.dry_run:
        print()
        print("=== dry run: the biggest 12 that would be attempted ===")
        for path, h, ext, nbytes, kind in sorted(todo, key=lambda t: -t[3])[:12]:
            print("  {:>9.1f} MB  {:<6} {}".format(
                nbytes / 1048576.0, kind, path[-72:]))
        oversize = [t for t in todo
                    if t[4] == "photo" and t[3] > a.max_photo_bytes]
        if oversize:
            print()
            print("  {} photo(s) over the {:.0f} MB cap would be skipped:".format(
                len(oversize), a.max_photo_bytes / 1048576.0))
            for path, h, ext, nbytes, kind in oversize:
                print("     {:>9.1f} MB  {}".format(nbytes / 1048576.0, path[-66:]))
        print()
        print("nothing was made.")
        return

    # P.AUDIT, not the enrichment store: paths.py has no constant for the store,
    # and D:\_PhotoAudit is where this project's run logs already live. Writing
    # to a non-existent attribute would have made every thumbnail and then
    # crashed recording them.
    logp = a.log or os.path.join(P.AUDIT, LOG)
    fresh = not os.path.exists(logp)
    os.makedirs(os.path.dirname(logp), exist_ok=True)
    counts: collections.Counter = collections.Counter()
    started = dt.datetime.now()

    with open(logp, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if fresh:
            w.writerow(LOG_COLS)
        for i, (path, h, ext, nbytes, kind) in enumerate(todo, 1):
            outcome, detail = one(path, h, ext, nbytes, kind, a.out, a.size,
                                  a.video_mode, a.max_photo_bytes)
            counts[outcome] += 1
            w.writerow([dt.datetime.now().isoformat(timespec="seconds"),
                        h, ext, nbytes, outcome, detail, path])
            if i % 50 == 0:
                lf.flush()
                rate = i / max((dt.datetime.now() - started).total_seconds(), 1)
                print("  {:,}/{:,}  made={:,} already={:,} skipped={:,} "
                      "failed={:,}  {:.1f}/s".format(
                          i, len(todo), counts["made"], counts["already"],
                          counts["skipped"], counts["failed"], rate),
                      flush=True)

    took = (dt.datetime.now() - started).total_seconds()
    print()
    print("attempted {:,} in {:.0f}s".format(len(todo), took))
    for k in ("made", "already", "skipped", "failed"):
        print("  {:<9} {:>6,}".format(k, counts[k]))
    print()
    print("outcomes logged to {}".format(logp))
    if counts["failed"] or counts["skipped"]:
        print("  A skip or a failure is a gap in what any classifier can see.")
        print("  Read the log: 0-byte files, `._` forks and AUD-*.3gp audio are")
        print("  correct refusals; a real photograph in there is a bug.")


if __name__ == "__main__":
    main()
