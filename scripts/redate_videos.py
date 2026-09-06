r"""Re-date library videos using the container's own creation_time.

The date chain is filename -> EXIF -> sidecar JSON -> folder name -> NoDate. EXIF
parsing only applies to JPEGs, and nothing ever calls ffprobe, so a video with no
date in its filename has never had its own metadata consulted. It was filed by the
name of the folder it arrived in.

That is how four diving videos ended up in 2022-01: they came out of an archive
named drive-download-20220107..., which is the date they were exported from Drive,
not the date they were shot.

A container's creation_time is written by the camera at the moment of recording. It
is far better evidence than the name of a folder someone made years later.

Guards on what it will accept:

  - the timestamp must be plausible (1995 .. today)
  - it must not be a known-bogus epoch value, which some muxers write
  - a file already dated from its own filename is never touched; the filename is
    higher in the precedence chain and is usually the camera's own naming

Reports first. Moves only with --apply, journalled, with the manifest updated so
the origin map follows.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

LIB = r"D:\PhotoLibrary\Library"
NODATE = r"D:\PhotoLibrary\NoDate"
MANIFEST = r"D:\PhotoLibrary\_Catalog\manifest.csv"
JOURNAL = r"D:\_PhotoAudit\video-redate.csv"
FFPROBE = (r"C:\Users\user\AppData\Local\Microsoft\WinGet\Packages"
           r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
           r"\ffmpeg-8.1.1-full_build\bin\ffprobe.exe")

VID = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".webm", ".wmv",
       ".mpg", ".mpeg", ".mts", ".m2ts")
NAME_DATE = re.compile(r"(?<!\d)(19|20)\d{6}(?!\d)")
YEAR_DIR = re.compile(r"Library\\(\d{4})\\(\d{4})-(\d{2})", re.I)

# Muxers that cannot read a clock write these. They are not dates.
BOGUS = {"1970-01-01", "1904-01-01", "2000-01-01", "1601-01-01"}


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def creation_time(path: str):
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format",
             "-show_streams", path],
            capture_output=True, text=True, timeout=60).stdout
        j = json.loads(out or "{}")
    except Exception:
        return None
    cands = []
    tags = (j.get("format") or {}).get("tags") or {}
    for k in ("creation_time", "com.apple.quicktime.creationdate", "date"):
        if tags.get(k):
            cands.append(tags[k])
    for s in j.get("streams", []):
        t = (s.get("tags") or {}).get("creation_time")
        if t:
            cands.append(t)
    for c in cands:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(c))
        if not m:
            continue
        if m.group(0) in BOGUS:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        if 1995 <= y <= dt.date.today().year and 1 <= mo <= 12:
            return f"{y:04d}", f"{mo:02d}"
    return None


def current_ym(path: str):
    m = YEAR_DIR.search(path)
    if m:
        return m.group(2), m.group(3)
    return ("NoDate", "") if path.startswith(NODATE) else (None, None)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    if not os.path.exists(FFPROBE):
        sys.exit(f"ffprobe not found at {FFPROBE}")

    targets = []
    for root in (LIB, NODATE):
        for dp, _, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                if fn.lower().endswith(VID) and not NAME_DATE.search(fn):
                    targets.append(os.path.join(dp, fn))
    print(f"{len(targets):,} videos with no date in their filename")
    print("probing containers...", flush=True)

    done = [0]

    def probe(p):
        r = creation_time(p)
        done[0] += 1
        if done[0] % 100 == 0:
            print(f"  {done[0]:,}/{len(targets):,} probed", flush=True)
        return p, r

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(probe, targets))

    moves, verdict = [], Counter()
    for p, r in results:
        if r is None:
            verdict["no usable timestamp"] += 1
            continue
        y, m = r
        cy, cm = current_ym(p)
        if cy == y and cm == m:
            verdict["already correct"] += 1
        elif cy == "NoDate":
            verdict["NoDate -> dated"] += 1
            moves.append((p, y, m, "NoDate"))
        elif cy is None:
            verdict["outside the library tree"] += 1
        else:
            verdict[f"misfiled"] += 1
            moves.append((p, y, m, f"{cy}-{cm}"))

    print()
    print("VERDICTS")
    print("-" * 66)
    for k, v in verdict.most_common():
        print(f"  {v:>6,}  {k}")

    print()
    print(f"{len(moves):,} files would move")
    for p, y, m, was in sorted(moves, key=lambda x: x[3])[:25]:
        print(f"  {was:>8} -> {y}-{m}  {os.path.basename(p)[:52]}")

    if not a.apply or not moves:
        print("\nReport only. Re-run with --apply." if not a.apply else "")
        return

    remap = {}
    new = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new:
            w.writerow(["From", "To", "WasDated", "NowDated", "Evidence", "When"])
        when = dt.datetime.now().isoformat(timespec="seconds")
        for p, y, m, was in moves:
            dest_dir = os.path.join(LIB, y, f"{y}-{m}")
            os.makedirs(lp(dest_dir), exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(p))
            stem, ext = os.path.splitext(dest)
            k = 0
            while os.path.exists(lp(dest)):
                k += 1
                dest = f"{stem}__{k}{ext}"
            w.writerow([p, dest, was, f"{y}-{m}",
                        "container creation_time via ffprobe", when])
            jf.flush()
            os.fsync(jf.fileno())
            try:
                shutil.move(lp(p), lp(dest))
                remap[p] = dest
            except OSError as e:
                print(f"  FAILED {p}: {e}")

    rows = []
    with open(MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if r and r[0] in remap:
                r[0] = remap[r[0]]
            rows.append(r)
    tmp = MANIFEST + ".new"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, MANIFEST)

    print(f"\nmoved {len(remap):,} files; manifest updated")
    print(f"journal: {JOURNAL}")


if __name__ == "__main__":
    main()
