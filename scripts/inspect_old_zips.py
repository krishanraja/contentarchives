r"""What is inside the old Takeout and Drive zips, and is any of it missing from the library?

These are 2022 Drive exports and a 2024 Google Takeout, sitting in laptop backup
folders. They predate the 2026 Takeout archives, so most of their contents should
already be in the library by another route - but "should be" is not evidence, and
the whole point of this project is that a zip is exactly where an unnoticed original
hides.

Reads the central directory only. Nothing is extracted, nothing is deleted. For
each media member it reports whether a file of that exact size already exists in the
library, which is the cheap first filter: a size that appears nowhere in the library
cannot be a duplicate, and is therefore something to look at.

Size is a filter, never a verdict. Anything flagged here gets a content hash before
any conclusion is drawn.
"""

from __future__ import annotations

import csv
import os
import tarfile
import zipfile
from collections import defaultdict

OUT = r"D:\_PhotoAudit\OLD-ZIP-CONTENTS.csv"
LIB_ROOTS = [r"D:\ContentLibrary", r"D:\ContentLibrary\ContentProduction", r"D:\ContentLibrary\Archive"]
SEARCH_ROOTS = ["D:\\"]
SKIP_DIRS = {"steamlibrary", "$recycle.bin", "system volume information", "archive",
             "photolibrary", "contentproduction"}

MEDIA_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp",
             ".tif", ".tiff", ".dng", ".cr2", ".nef", ".arw", ".mp4", ".mov",
             ".avi", ".mkv", ".m4v", ".3gp", ".webm", ".wmv", ".mpg", ".mpeg"}
ARCHIVE_RE = (".zip", ".tgz", ".tar.gz")


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def find_archives() -> list[str]:
    found = []
    for root in SEARCH_ROOTS:
        for dp, dirnames, fns in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
            for fn in fns:
                low = fn.lower()
                if low.endswith(ARCHIVE_RE) and (
                        "takeout" in low or "drive-download" in low):
                    found.append(os.path.join(dp, fn))
    return sorted(found)


def library_sizes() -> set[int]:
    sizes = set()
    for root in LIB_ROOTS:
        for dp, _, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                try:
                    sizes.add(os.path.getsize(lp(os.path.join(dp, fn))))
                except OSError:
                    pass
    return sizes


def members(path: str):
    low = path.lower()
    try:
        if low.endswith(".zip"):
            with zipfile.ZipFile(lp(path)) as z:
                for i in z.infolist():
                    if not i.is_dir():
                        yield i.filename, i.file_size
        else:
            with tarfile.open(lp(path), "r:*") as t:
                for m in t:
                    if m.isfile():
                        yield m.name, m.size
    except Exception as e:
        print(f"  UNREADABLE {path}: {e}")


def main() -> None:
    archives = find_archives()
    print(f"found {len(archives)} old export archives")
    for a in archives:
        try:
            print(f"  {os.path.getsize(lp(a))/1024**3:>6.2f} GB  {a}")
        except OSError:
            print(f"  {'?':>6}     {a}")

    print("\nindexing library file sizes...")
    sizes = library_sizes()
    print(f"  {len(sizes):,} distinct sizes in the library")

    rows = []
    per_archive = defaultdict(lambda: {"media": 0, "media_b": 0,
                                       "novel": 0, "novel_b": 0, "other": 0})
    print("\nreading central directories...")
    for a in archives:
        for name, size in members(a):
            ext = os.path.splitext(name)[1].lower()
            e = per_archive[a]
            if ext not in MEDIA_EXT:
                e["other"] += 1
                continue
            e["media"] += 1
            e["media_b"] += size
            novel = size not in sizes
            if novel:
                e["novel"] += 1
                e["novel_b"] += size
            rows.append([a, name, size, ext, "no-size-match" if novel else "size-match"])
        d = per_archive[a]
        print(f"  {os.path.basename(a)[:52]:<52} media {d['media']:>6,}  "
              f"no size match {d['novel']:>5,} ({d['novel_b']/1024**2:>8.1f} MB)")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Archive", "Member", "Bytes", "Ext", "SizeCheck"])
        w.writerows(rows)

    tot_media = sum(d["media"] for d in per_archive.values())
    tot_novel = sum(d["novel"] for d in per_archive.values())
    tot_novel_b = sum(d["novel_b"] for d in per_archive.values())
    print()
    print("=" * 84)
    print(f"  {tot_media:,} media members across {len(archives)} archives")
    print(f"  {tot_novel:,} ({tot_novel_b/1024**3:.2f} GB) have a size matching "
          f"NOTHING in the library")
    print("=" * 84)
    if tot_novel:
        print("\n  Those need extracting and hashing before any archive is deleted.")
        print("  Largest:")
        for r in sorted((r for r in rows if r[4] == "no-size-match"),
                        key=lambda r: -r[2])[:20]:
            print(f"    {r[2]/1024**2:>8.1f} MB  {os.path.basename(r[0])[:34]:<34} {r[1][:44]}")
    else:
        print("\n  Every media member matches a size already in the library.")
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
