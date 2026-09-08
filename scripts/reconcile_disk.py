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
import os

AUDIT = r"D:\_PhotoAudit"
INVENTORY = os.path.join(AUDIT, "INVENTORY.csv")
ORIGIN_MAP = os.path.join(AUDIT, "ORIGIN-MAP.csv")
ORPHANS = os.path.join(AUDIT, "DISK-NOT-IN-INVENTORY.csv")

# Every root that holds content we care about keeping.
ROOTS = [r"D:\ContentLibrary"]   # one root now: Archive and ContentProduction live inside it

MEDIA = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.bmp', '.tif',
         '.tiff', '.webp', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.mp4',
         '.mov', '.avi', '.m2ts', '.3gp', '.mkv', '.wmv', '.m4v', '.mpg',
         '.mpeg', '.webm', '.mts'}


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="append orphans to the inventory as unclassified rows")
    ap.add_argument("--all-types", action="store_true",
                    help="include non-media files too")
    a = ap.parse_args()

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
                row = [""] * 23
                row[0] = p
                rel = os.path.relpath(p, "D:\\").split(os.sep)
                row[1] = rel[1] if len(rel) > 1 else ""
                row[4], row[6] = e, s
                row[5] = "photo" if e in MEDIA else "other"
                row[22] = "reconciled-from-disk"
                w.writerow(row)
        print(f"\nappended {len(orphans):,} orphan rows to the inventory")


if __name__ == "__main__":
    main()
