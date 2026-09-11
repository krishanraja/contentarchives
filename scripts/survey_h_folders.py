r"""Read the NAMES on H: and nothing else, to find out what is actually there.

from-machine-b turned out to be 79% development artifacts - QA screenshots of the
user's own apps, path-flattened Downloads, business videos - not memories. That
was found by ingesting 7 GB and looking. Finding the same thing at 288 GB would
cost eight hours and pollute the chronology.

So: walk the mount for names and sizes only. os.walk and getsize read directory
metadata; they do not open files, so nothing hydrates and nothing is downloaded.

Every file is scored against path signatures. The point is not to auto-delete
anything - it is to say, per folder, "this one is a camera dump" or "this one is
a laptop backup", so the ingest can route instead of dumping.
"""

from __future__ import annotations

import collections
import os
import re
import sys

H_ROOT = r"H:\My Drive\_photo-consolidation"
NEVER = {".lrv", ".lrf", ".thm", ".db", ".ini"}

# Signatures learned from from-machine-b, kept deliberately narrow. A file is only
# called work if its PATH says so - never on extension alone, because .png is
# both a QA screenshot and a scanned childhood photo.
WORK = re.compile(
    r"(qa-|uxtest|pwtest|prerender|-qa\b|qa_|shots?[\\/_]|screenshot|"
    r"PROJECT-A|mindmake|PROJECT-B|mm-ctrl|circle-qa|cc-uxtest|ctrl-corpus|"
    r"EMPLOYER-B|riverside|loom|node_modules|\.git[\\/]|downloads)", re.I)
CAMERA = re.compile(
    r"(dcim|gopro|gx\d{6}|dji_|100media|100_|\bimg_\d{4}|\bdsc\d{4}|"
    r"\bp\d{7}|vid_\d{8}|\d{8}_\d{6}|photo-\d{4}-\d{2}|camera)", re.I)
DATED = re.compile(r"(19|20)\d{2}[-_.]?(0[1-9]|1[0-2])")

MEDIA = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp",
         ".tif", ".tiff", ".dng", ".cr2", ".nef", ".arw", ".raf", ".orf",
         ".mp4", ".mov", ".avi", ".mts", ".m2ts", ".m4v", ".3gp", ".mpg",
         ".mpeg", ".wmv", ".mkv", ".mod", ".webm", ".flv"}


def survey(folder: str) -> None:
    root = os.path.join(H_ROOT, folder)
    n = work = camera = dated = nonmedia = 0
    by_ext: collections.Counter = collections.Counter()
    work_bytes = cam_bytes = other_bytes = 0
    samples_work: list[str] = []
    samples_other: list[str] = []

    for dp, dns, fns in os.walk(root):
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            if ext in NEVER:
                continue
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if sz == 0:
                continue
            n += 1
            by_ext[ext] += 1
            if ext not in MEDIA:
                nonmedia += 1
            rel = os.path.relpath(p, root)
            is_w = bool(WORK.search(rel))
            is_c = bool(CAMERA.search(rel))
            if DATED.search(rel):
                dated += 1
            # camera evidence outranks work evidence: DCIM\...\Downloads is a
            # camera file that passed through a downloads folder, not a QA shot
            if is_c:
                camera += 1
                cam_bytes += sz
            elif is_w:
                work += 1
                work_bytes += sz
                if len(samples_work) < 6:
                    samples_work.append(rel[:88])
            else:
                other_bytes += sz
                if len(samples_other) < 8:
                    samples_other.append(rel[:88])

    gb = lambda b: b / 1024 ** 3                                   # noqa: E731
    print(f"\n=== {folder}")
    print(f"  files {n:,}   total {gb(work_bytes+cam_bytes+other_bytes):.1f} GB")
    print(f"  camera-signature : {camera:>7,}  ({gb(cam_bytes):.1f} GB)")
    print(f"  work-signature   : {work:>7,}  ({gb(work_bytes):.1f} GB)")
    print(f"  neither          : {n-camera-work:>7,}  ({gb(other_bytes):.1f} GB)")
    print(f"  name carries a date: {dated:,}   non-media extensions: {nonmedia:,}")
    print(f"  top ext: {dict(by_ext.most_common(8))}")
    if samples_work:
        print("  work samples:")
        for s in samples_work:
            print(f"     {s}")
    if samples_other:
        print("  'neither' samples:")
        for s in samples_other:
            print(f"     {s}")


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in sorted(os.listdir(H_ROOT))
                               if os.path.isdir(os.path.join(H_ROOT, d))]
    print(f"surveying {len(folders)} folder(s) on {H_ROOT}")
    print("names and sizes only - no file is opened, nothing hydrates")
    for f in folders:
        survey(f)
