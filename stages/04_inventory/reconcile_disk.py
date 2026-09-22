r"""The disk is the truth. The inventory is a claim about it.

Where they disagree, the DISK WINS and the record is corrected. A file is never
deleted, deprioritised, or excluded because it is missing from an index.

WHY THIS EXISTS

Two failures, one day apart, from the same root:

  - The dedup index covered 12% of the library. Files it could not see were
    treated as absent, and 21,649 duplicates were admitted because the settled
    copy was invisible to the lookup.
  - The original source inventory was overwritten by a tool writing a filename
    that already existed under different case. The record of a 200,000-file
    process was destroyed by one careless write.

Both are the same mistake in different directions: TRUSTING A DERIVED RECORD
OVER THE THING IT DESCRIBES. An index is a cache of the filesystem, it is
always at least slightly wrong, and the moment it is treated as authoritative
it starts making decisions the filesystem would not.

So this walks the disk, compares against every record we hold, and reports what
the records missed. The output is always ADDITIVE: unknown files are candidates
for inclusion, never for removal.

    python reconcile_disk.py                 # report
    python reconcile_disk.py --write         # append the orphans to the inventory
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives

AUDIT = r"D:\_PhotoAudit"
INVENTORY = os.path.join(AUDIT, "INVENTORY.csv")
ORIGIN_MAP = os.path.join(AUDIT, "ORIGIN-MAP.csv")
ORPHANS = os.path.join(AUDIT, "DISK-NOT-IN-INVENTORY.csv")

# Every root that holds content we care about keeping.
ROOTS = [r"D:\ContentLibrary"]   # one root now: Archive and ContentProduction live inside it
LIB_ROOT = ROOTS[0]

MEDIA = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.bmp', '.tif',
         '.tiff', '.webp', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.mp4',
         '.mov', '.avi', '.m2ts', '.3gp', '.mkv', '.wmv', '.m4v', '.mpg',
         '.mpeg', '.webm', '.mts'}

# MEDIA above is photos AND videos, so `"photo" if ext in MEDIA` called every
# .mp4 a photograph - 4,344 of them in the rows this tool had already written.
VIDEO = {'.mp4', '.mov', '.avi', '.m2ts', '.3gp', '.mkv', '.wmv', '.m4v',
         '.mpg', '.mpeg', '.webm', '.mts'}

# The chronology is one level deep since 2026-09-21: `Media\<Side>\YYYY\`.
YEAR_RX = re.compile("\\\\(19[89]\\d|20[0-9]\\d)\\\\")


def row_for(path, size, ext):
    r"""The inventory row an orphan deserves, derived from its own path.

    THREE THINGS WERE WRONG HERE, and all three were silent.

    `Side` IS THE TOP-LEVEL TREE, and it merely looks like it should be the
    side. `build_inventory.py`, which owns the column, writes `rel[0]`:
    "Media", "Archive", "_Review", "ContentProduction". It is NOT
    Personal/Communal. `people_sheet.py` carries the scar - a filter that
    joined on it "found no cluster with a Personal photograph, and would have
    excluded all 58,033" (learning 54). Those live one level further down and
    are read from the PATH by `side_of`, never from this column. Making it
    hold a real side is not a repair: it breaks the contract every reader
    relies on and leaves one column meaning two things in one file. This was
    changed to `side_of` on 2026-09-22 and changed straight back.

    `Year` and `Month` were left empty although the path names the year, so
    11,742 files went into the index undated and invisible to every query that
    asks when. The month is genuinely absent now and stays empty - the
    chronology is one level deep, and inventing one would be worse than
    admitting it.

    `Kind` was `"photo" if ext in MEDIA`, and MEDIA holds videos too, so every
    video was filed as a photograph.

    None of these raised anything. The rows appended cleanly and the counts
    added up; only the meaning was wrong.
    """
    m = YEAR_RX.search(path)
    kind = "video" if ext in VIDEO else ("photo" if ext in MEDIA else "other")
    row = [""] * 23
    row[0] = path
    # The tree, matching build_inventory's `rel[0]` - see the docstring.
    rel = os.path.relpath(path, LIB_ROOT).split(os.sep)
    row[1] = rel[0] if len(rel) > 1 else ""
    row[2] = m.group(1) if m else ""
    row[4], row[5], row[6] = ext, kind, size
    row[22] = "reconciled-from-disk"
    return row


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def known_paths() -> set[str]:
    """Everything any record claims exists. Case-folded, because the
    filesystem is case-insensitive and a record that differs only in case
    describes the same file - the lesson that cost us inventory.csv."""
    known: set[str] = set()
    for f, col in ((INVENTORY, "LibraryPath"), (ORIGIN_MAP, "LibraryPath")):
        if not os.path.exists(f):
            continue
        with open(f, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                v = (r.get(col) or "").strip()
                if v:
                    known.add(os.path.normcase(os.path.abspath(v)))
    return known


def repair_rows():
    r"""Correct the rows this tool wrote before `row_for` existed.

    Fixing the writer does nothing for the 11,742 rows already in the
    inventory, and those rows are what the index is built from. They are
    identifiable without guessing: this tool stamps `reconciled-from-disk` into
    the last column, so the repair touches exactly its own output and nothing
    a person or another stage wrote.

    Rewritten through a temp file and os.replace, because the original source
    inventory was once destroyed by a tool writing a name that already existed
    (this file's own docstring), and a half-written INVENTORY.csv is the record
    of a 200,000-file process.
    """
    import shutil
    rows, fixed = [], 0
    with io.open(INVENTORY, encoding="utf-8", errors="replace", newline="") as f:
        rd = csv.reader(f)
        header = next(rd)
        for r in rd:
            if len(r) >= 23 and r[22] == "reconciled-from-disk":
                was = (r[1], r[2], r[5])
                r = row_for(r[0], r[6], (r[4] or "").lower())
                if (r[1], r[2], r[5]) != was:
                    fixed += 1
            rows.append(r)

    backup = INVENTORY + ".prerepair"
    if not os.path.exists(backup):
        shutil.copy2(INVENTORY, backup)
        print("backed up the inventory as it stood -> {}".format(backup))
    tmp = INVENTORY + ".new"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INVENTORY)
    print("repaired {:,} of {:,} rows".format(fixed, len(rows)))
    print("Now rebuild the index: python stages/08_index/build_db.py")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="append orphans to the inventory as unclassified rows")
    ap.add_argument("--all-types", action="store_true",
                    help="include non-media files too")
    ap.add_argument("--repair", action="store_true",
                    help="re-derive Side, Year and Kind on rows this tool "
                         "wrote earlier with the wrong ones, in place. Reads "
                         "nothing but the path, writes no new rows, and "
                         "leaves every other row untouched.")
    a = ap.parse_args()

    if a.repair:
        return repair_rows()

    known = known_paths()
    print(f"records claim {len(known):,} distinct paths")

    orphans = []
    seen = walked = 0
    for root in ROOTS:
        if not os.path.isdir(lp(root)):
            continue
        for dp, dns, fns in os.walk(lp(root)):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                p = os.path.join(dp, fn).replace("\\\\?\\", "")
                walked += 1
                ext = os.path.splitext(fn)[1].lower()
                if not a.all_types and ext not in MEDIA:
                    continue
                seen += 1
                if os.path.normcase(os.path.abspath(p)) in known:
                    continue
                try:
                    sz = os.path.getsize(lp(p))
                except OSError:
                    continue
                orphans.append((p, sz, ext))

    print(f"walked {walked:,} files ({seen:,} media)")
    print(f"\nON DISK BUT IN NO RECORD: {len(orphans):,} files, "
          f"{sum(s for _, s, _ in orphans)/1024**3:.2f} GB")

    if orphans:
        by = collections.Counter()
        for p, s, e in orphans:
            rel = os.path.relpath(p, "D:\\").split(os.sep)
            by[os.sep.join(rel[:2])] += 1
        print("\n  where they are:")
        for k, v in by.most_common(12):
            print(f"     {v:>7,}  {k}")
        with open(ORPHANS, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Path", "Bytes", "Ext"])
            w.writerows(orphans)
        print(f"\n  listed: {ORPHANS}")

    print("\nThese are files the records do not know about. They are CANDIDATES")
    print("FOR INCLUSION, never for removal. Nothing here is evidence that a")
    print("file is unwanted - only that an index is incomplete.")

    if a.write and orphans:
        with open(INVENTORY, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for p, s, e in orphans:
                w.writerow(row_for(p, s, e))
        print(f"\nappended {len(orphans):,} orphan rows to the inventory")


if __name__ == "__main__":
    main()
