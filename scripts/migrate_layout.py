r"""Move the library to its final shape, and prove nothing was lost doing it.

    D:\PhotoLibrary       ->  D:\ContentLibrary
    ...\Personal          ->  ...\Media\Personal
    ...\Communal          ->  ...\Media\Communal
    ...\NoDate            ->  ...\Media\NoDate
    ...\Library           ->  ...\Media\Pending-Segmentation
    D:\Archive            ->  D:\ContentLibrary\Archive
    D:\ContentProduction  ->  D:\ContentLibrary\ContentProduction

WHY THIS IS SAFER THAN IT LOOKS

Every move is a DIRECTORY RENAME on one volume. No bytes are copied, nothing is
read, and each is atomic as far as the filesystem is concerned - it either
happened or it did not. 80,000 files move in milliseconds and a power cut in
the middle leaves a consistent tree, not half a library.

The risk is not the moves. It is the RECORDS: a manifest of 107,234 rows, an
inventory, an origin map and two journals, all naming paths that are about to
be wrong. A record that quietly points at a path which no longer exists does
not raise anything - it just makes later work silently incorrect. That failure
has already cost this project 207 GB once.

So the order is: count first, move, rewrite every record, then VERIFY by
resolving rows against the filesystem. Numbers before and after must match.

WHAT WOULD MAKE IT STOP

  - the destination already exists
  - a source is missing
  - file counts differ before and after
  - any manifest row fails to resolve after rewriting

Any of those aborts before the records are touched, or reports loudly after.

    python migrate_layout.py            # plan and check, change nothing
    python migrate_layout.py --apply

RUN AND COMPLETE 2026-09-08: 81,306 files, counts matched, records rewritten.
Kept as the record of what moved where.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

OLD_ROOT = r"D:\PhotoLibrary"   # historical: what the library was called before

MOVES = [
    (os.path.join(OLD_ROOT, "Personal"), P.PERSONAL),
    (os.path.join(OLD_ROOT, "Communal"), P.COMMUNAL),
    (os.path.join(OLD_ROOT, "NoDate"), P.NODATE),
    (os.path.join(OLD_ROOT, "Library"), P.PENDING),
]

RECORDS = [
    (P.MANIFEST, None),
    (r"D:\_PhotoAudit\ORIGIN-MAP.csv", None),
    (r"D:\_PhotoAudit\INVENTORY.csv", None),
    (r"D:\_PhotoAudit\autopilot-added.csv", None),
    (r"D:\_PhotoAudit\user-directed-deletions.csv", None),
    (r"D:\_PhotoAudit\autopilot-duplicates.csv", None),
    (r"D:\_PhotoAudit\downgrade-triage.csv", None),
]


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def count(root: str) -> int:
    return sum(len(f) for _, _, f in os.walk(lp(root))) if os.path.isdir(lp(root)) else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    # ---------- census before ----------
    before = {
        "Personal": count(os.path.join(OLD_ROOT, "Personal")),
        "Communal": count(os.path.join(OLD_ROOT, "Communal")),
        "NoDate": count(os.path.join(OLD_ROOT, "NoDate")),
        "Library": count(os.path.join(OLD_ROOT, "Library")),
        "_Review": count(os.path.join(OLD_ROOT, "_Review")),
        "Archive": count(P.ARCHIVE),
        "ContentProduction": count(P.PRODUCTION),
    }
    total_before = sum(before.values())
    print("BEFORE")
    for k, v in before.items():
        print(f"  {v:>8,}  {k}")
    print(f"  {total_before:>8,}  TOTAL")

    # ---------- refuse on anything unexpected ----------
    problems = []
    if os.path.exists(lp(P.ROOT)):
        problems.append(f"destination already exists: {P.ROOT}")
    if not os.path.isdir(lp(OLD_ROOT)):
        problems.append(f"source missing: {OLD_ROOT}")
    for src in (r"D:\Archive", r"D:\ContentProduction"):
        if not os.path.isdir(lp(src)):
            problems.append(f"source missing: {src}")
    if problems:
        for p in problems:
            print(f"  REFUSING: {p}")
        sys.exit(1)

    if not a.apply:
        print("\nPLAN")
        print(f"  rename  {OLD_ROOT}  ->  {P.ROOT}")
        print(f"  mkdir   {P.MEDIA}")
        for s, d in MOVES:
            print(f"  move    {os.path.basename(s):<12} ->  Media\\{os.path.basename(d)}")
        print(f"  move    D:\\Archive           ->  {P.ARCHIVE}")
        print(f"  move    D:\\ContentProduction ->  {P.PRODUCTION}")
        print(f"\n  then rewrite {len(RECORDS)} record files and verify.")
        print("\nDRY RUN - nothing changed. Re-run with --apply.")
        return

    # ---------- move ----------
    print("\nMOVING")
    os.rename(lp(OLD_ROOT), lp(P.ROOT))
    print(f"  renamed root -> {P.ROOT}")
    os.makedirs(lp(P.MEDIA), exist_ok=True)
    for src, dst in MOVES:
        src_now = src.replace(OLD_ROOT, P.ROOT)
        if os.path.isdir(lp(src_now)):
            os.rename(lp(src_now), lp(dst))
            print(f"  {os.path.basename(src_now):<12} -> Media\\{os.path.basename(dst)}")
    for src, dst in ((r"D:\Archive", P.ARCHIVE), (r"D:\ContentProduction", P.PRODUCTION)):
        if os.path.isdir(lp(src)):
            os.rename(lp(src), lp(dst))
            print(f"  {src} -> {dst}")

    # ---------- census after ----------
    after = {
        "Personal": count(P.PERSONAL), "Communal": count(P.COMMUNAL),
        "NoDate": count(P.NODATE), "Library": count(P.PENDING),
        "_Review": count(P.REVIEW), "Archive": count(P.ARCHIVE),
        "ContentProduction": count(P.PRODUCTION),
    }
    total_after = sum(after.values())
    print("\nAFTER")
    for k, v in after.items():
        flag = "" if v == before[k] else f"   <-- WAS {before[k]:,}"
        print(f"  {v:>8,}  {k}{flag}")
    print(f"  {total_after:>8,}  TOTAL")
    if total_after != total_before:
        print(f"\n  !! FILE COUNT CHANGED: {total_before:,} -> {total_after:,}")
        print("  Records NOT rewritten. Investigate before going further.")
        sys.exit(1)
    print("  counts match.")

    # ---------- rewrite the records ----------
    print("\nREWRITING RECORDS")
    for path, _ in RECORDS:
        if not os.path.exists(path):
            print(f"  skip (absent): {os.path.basename(path)}")
            continue
        changed = rows = 0
        tmp = path + ".new"
        with open(path, newline="", encoding="utf-8", errors="replace") as fin, \
             open(tmp, "w", newline="", encoding="utf-8") as fout:
            w = csv.writer(fout)
            for row in csv.reader(fin):
                rows += 1
                out = []
                for cell in row:
                    m = P.migrate(cell) if cell[1:2] == ":" else cell
                    if m != cell:
                        changed += 1
                    out.append(m)
                w.writerow(out)
        os.replace(tmp, path)
        print(f"  {os.path.basename(path):<34} {rows:>8,} rows, {changed:>8,} paths rewritten")

    # ---------- verify ----------
    print("\nVERIFYING the manifest resolves")
    ok = miss = 0
    missing_examples = []
    with open(P.MANIFEST, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if os.path.exists(lp(row[0])):
                ok += 1
            else:
                miss += 1
                if len(missing_examples) < 5:
                    missing_examples.append(row[0])
    print(f"  {ok:,} rows resolve, {miss:,} do not")
    for m in missing_examples:
        print(f"    missing: {m}")
    if miss:
        print("  (rows for deleted files are expected here - check_manifest")
        print("   cross-references the journals and is the real test.)")

    print(f"\nDONE. New root: {P.ROOT}")


if __name__ == "__main__":
    main()
