r"""Where is the space on D: actually going, and how much can genuinely be freed?

The intuition that a consolidated library leaves duplicate originals behind is
wrong here, and expensively so: 26,576 library files are hardlinks. A hardlink is a
second *name* for one set of bytes, so those bytes are already counted once, and
deleting the "original" frees nothing at all while the library name survives.

This walks the volume counting each inode once, and splits every file into:

  linked    the bytes are also reachable from the library. Deleting the outside
            name frees NOTHING. Safe, pointless.
  library   only reachable from the library, ContentProduction or staging. This is
            the collection. Not a candidate.
  free      only reachable from outside the library. These are the real bytes -
            deleting them actually returns space.

Read-only. It deletes nothing and proposes nothing; it reports.
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

ROOT = "D:\\"
LIBRARY_ROOTS = [
    r"D:\ContentLibrary",
    r"D:\ContentLibrary\ContentProduction",
]
# Working areas - not the collection, but not junk either. Reported separately.
WORK_ROOTS = [
    r"D:\_PhotoAudit",
    r"D:\_Staging",
    r"D:\_machine-b_stage",
    r"D:\_takeout_tmp",
    r"D:\_machine-b_tmp",
    r"D:\Takeout",
]

MEDIA_EXT = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp", ".tif",
    ".tiff", ".dng", ".raw", ".cr2", ".nef", ".arw", ".mp4", ".mov", ".avi",
    ".mkv", ".m4v", ".mts", ".3gp", ".webm", ".wmv", ".mpg", ".mpeg", ".flv",
}

OUT_DIR = r"D:\_PhotoAudit"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def under(path: str, roots: list[str]) -> bool:
    low = path.lower()
    return any(low.startswith(r.lower() + "\\") or low == r.lower() for r in roots)


def top_level(path: str) -> str:
    rest = path[len(ROOT):]
    parts = rest.split("\\")
    return parts[0] if len(parts) > 1 else "(files at D:\\ root)"


def main() -> None:
    # inode -> {size, names:[...], in_lib:bool, in_work:bool, outside:[...]}
    inodes: dict[tuple, dict] = {}
    errors = 0
    seen = 0

    for dirpath, dirnames, filenames in os.walk(ROOT):
        if "$RECYCLE.BIN" in dirpath or "System Volume Information" in dirpath:
            dirnames[:] = []
            continue
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(lp(full))
            except OSError:
                errors += 1
                continue
            seen += 1
            if seen % 50000 == 0:
                print(f"  scanned {seen:,} files...", flush=True)
            key = (st.st_dev, st.st_ino)
            e = inodes.get(key)
            if e is None:
                e = inodes[key] = {"size": st.st_size, "lib": False,
                                   "work": False, "outside": []}
            if under(full, LIBRARY_ROOTS):
                e["lib"] = True
            elif under(full, WORK_ROOTS):
                e["work"] = True
                e["outside"].append(full)
            else:
                e["outside"].append(full)

    print(f"\n{seen:,} file names, {len(inodes):,} distinct inodes, {errors:,} unreadable")

    # --- classify -----------------------------------------------------------
    cat_bytes = defaultdict(int)
    cat_files = defaultdict(int)
    folder = defaultdict(lambda: {"free": 0, "linked": 0, "n": 0})
    freeable = []

    for e in inodes.values():
        size = e["size"]
        if e["lib"] and e["outside"]:
            cat = "linked"                     # deleting the outside name frees 0
        elif e["lib"]:
            cat = "library"
        elif e["work"]:
            cat = "working"
        else:
            cat = "free"
        cat_bytes[cat] += size
        cat_files[cat] += 1

        for name in e["outside"]:
            t = top_level(name)
            folder[t]["n"] += 1
            if cat == "linked":
                folder[t]["linked"] += size
            elif cat in ("free", "working"):
                folder[t]["free"] += size
            break                              # count each inode once per folder

        if cat in ("free", "working") and e["outside"]:
            p = e["outside"][0]
            freeable.append((size, p, os.path.splitext(p)[1].lower(), cat))

    total = sum(cat_bytes.values())
    print()
    print("WHERE THE BYTES ARE  (each inode counted once)")
    print("=" * 78)
    for cat, label in [
        ("library", "in the library only          - the collection"),
        ("linked", "hardlinked into the library  - DELETING FREES NOTHING"),
        ("working", "working/staging areas        - freeable"),
        ("free", "outside the library          - freeable"),
    ]:
        print(f"  {label:<58} {cat_bytes[cat]/1024**3:>8.1f} GB  {cat_files[cat]:>7,}")
    print(f"  {'TOTAL':<58} {total/1024**3:>8.1f} GB  {sum(cat_files.values()):>7,}")
    print()
    print(f"  MAXIMUM RECLAIMABLE without touching the library: "
          f"{(cat_bytes['free'] + cat_bytes['working'])/1024**3:.1f} GB")

    # --- by folder ----------------------------------------------------------
    print()
    print("BY TOP-LEVEL FOLDER  (freeable = bytes that only exist here)")
    print("=" * 78)
    print(f"  {'freeable':>10} {'linked':>10}   folder")
    print("  " + "-" * 74)
    rows = sorted(folder.items(), key=lambda kv: -kv[1]["free"])
    for name, d in rows[:40]:
        if d["free"] < 100 * 1024**2 and d["linked"] < 100 * 1024**2:
            continue
        print(f"  {d['free']/1024**3:>9.1f}G {d['linked']/1024**3:>9.1f}G   {name}")

    # --- biggest individual wins -------------------------------------------
    freeable.sort(reverse=True)
    print()
    print("LARGEST FREEABLE FILES  (not in the library, not hardlinked to it)")
    print("=" * 78)
    for size, p, ext, cat in freeable[:40]:
        kind = "media" if ext in MEDIA_EXT else "other"
        print(f"  {size/1024**3:>7.2f} GB  {kind:<6} {p[:88]}")

    # --- by extension, for the non-media bulk -------------------------------
    ext_b = defaultdict(int)
    ext_n = defaultdict(int)
    for size, p, ext, cat in freeable:
        ext_b[ext] += size
        ext_n[ext] += 1
    print()
    print("FREEABLE BY EXTENSION")
    print("=" * 78)
    for ext, b in sorted(ext_b.items(), key=lambda kv: -kv[1])[:25]:
        kind = "media" if ext in MEDIA_EXT else ""
        print(f"  {b/1024**3:>8.2f} GB  {ext_n[ext]:>7,}  {ext or '(none)':<12} {kind}")

    out = os.path.join(OUT_DIR, "SPACE-FREEABLE.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Bytes", "Path", "Ext", "Category", "IsMedia"])
        for size, p, ext, cat in freeable:
            w.writerow([size, p, ext, cat, ext in MEDIA_EXT])
    print()
    print(f"written: {out}  ({len(freeable):,} rows)")


if __name__ == "__main__":
    main()
