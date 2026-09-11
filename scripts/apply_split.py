r"""Split the chronology into Personal and Communal, by origin folder.

    PhotoLibrary\Personal\YYYY\YYYY-MM\
    PhotoLibrary\Communal\YYYY\YYYY-MM\
    PhotoLibrary\Personal\NoDate\  and  Communal\NoDate\
    PhotoLibrary\Library\...            anything still unassigned

Anything whose origin is not confidently assigned **stays where it is**. The
residual `Library\` tree is then a visible to-do list rather than a silent guess.
That is the point: a wrong assignment here becomes invisible the moment the file
moves, so nothing gets assigned on a hunch.

Moves are same-volume renames: instant, no extra space, and they cannot half-copy.
Every move is journalled before it happens and the manifest is rewritten to follow,
so the origin map stays true.

    python apply_split.py            # report
    python apply_split.py --apply
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import re
import shutil
import sys
from collections import defaultdict

LIBROOT = r"D:\ContentLibrary"
LIB = os.path.join(LIBROOT, "Library")
NODATE = os.path.join(LIBROOT, "NoDate")
ORIGIN = r"D:\_PhotoAudit\ORIGIN-MAP.csv"
PROPOSAL = r"D:\_PhotoAudit\SPLIT-PROPOSAL.csv"
MANIFEST = os.path.join(LIBROOT, "_Catalog", "manifest.csv")
JOURNAL = r"D:\_PhotoAudit\chronology-split.csv"
ARCHIVE_WORK = r"D:\ContentLibrary\Archive\06-Work"

# Decided by the user, 2026-09-06. Origin folders the path signals could not
# settle, resolved by the person whose memories these are.
OVERRIDES = [
    # (regex on the origin folder, side)
    (re.compile(r"D:\\UK December 2015", re.I), "personal"),
    (re.compile(r"D:\\Val D'Isere December 2015", re.I), "personal"),
    (re.compile(r"D:\\india\b", re.I), "personal"),
    (re.compile(r"Queenstown", re.I), "personal"),
    (re.compile(r"ridiculous obstacle", re.I), "personal"),
    # recorded family video calls, sitting in a work backup folder
    (re.compile(r"work backup 2022\\Videos\\Captures", re.I), "personal"),
    # produced work media - not memories at all, so out of the chronology
    (re.compile(r"Sizzle|AMP Video|Audience & Data|\\Zoom\\", re.I), "archive-work"),
    (re.compile(r"work backup 201\d\\documents", re.I), "archive-work"),
    # the diving footage, extracted from a 2022 Drive export
    (re.compile(r"_zip_extract", re.I), "personal"),
]


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def side_for(folder: str, base: dict[str, str]) -> str:
    for rx, side in OVERRIDES:
        if rx.search(folder):
            return side
    return base.get(folder, "unclear")


def main() -> None:
    apply = "--apply" in sys.argv

    base = {}
    with open(PROPOSAL, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            base[r["OriginFolder"]] = r["Side"]

    plan = []
    counts = defaultdict(lambda: [0, 0])
    with open(ORIGIN, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            rel = r["LibraryPath"]
            if not (rel.startswith("Library") or rel.startswith("NoDate")):
                continue
            src = os.path.join(LIBROOT, rel)
            side = side_for(r["OriginFolder"], base)
            size = int(r["Bytes"] or 0)
            counts[side][0] += 1
            counts[side][1] += size
            if side == "unclear":
                continue

            parts = rel.split("\\")
            if side == "archive-work":
                leaf = re.sub(r'[<>:"/\\|?*]+', "_",
                              os.path.basename(r["OriginFolder"]))[:60] or "misc"
                dest = os.path.join(ARCHIVE_WORK, leaf, parts[-1])
            elif parts[0] == "NoDate":
                dest = os.path.join(LIBROOT, side.capitalize(), "NoDate", parts[-1])
            else:                                   # Library\YYYY\YYYY-MM\file
                dest = os.path.join(LIBROOT, side.capitalize(), *parts[1:])
            plan.append((src, dest, side, size))

    print("CHRONOLOGY SPLIT")
    print("=" * 72)
    for side in ("personal", "communal", "archive-work", "unclear"):
        n, b = counts[side]
        note = "  <- stays in Library\\, needs a person" if side == "unclear" else ""
        print(f"  {side:<14} {n:>7,} files  {b/1024**3:>7.2f} GB{note}")
    print()
    print(f"{len(plan):,} files would move")

    if not apply:
        print("\nReport only. Re-run with --apply.")
        return

    moved, failed = {}, 0
    new = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new:
            w.writerow(["From", "To", "Side", "Bytes", "When"])
        when = dt.datetime.now().isoformat(timespec="seconds")
        for i, (src, dest, side, size) in enumerate(plan, 1):
            if i % 5000 == 0:
                print(f"  {i:,}/{len(plan):,} moved", flush=True)
            if not os.path.exists(lp(src)):
                continue
            os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
            d = dest
            stem, ext = os.path.splitext(d)
            k = 0
            while os.path.exists(lp(d)):
                k += 1
                d = f"{stem}__{k}{ext}"
            w.writerow([src, d, side, size, when])
            if i % 500 == 0:
                jf.flush()
                os.fsync(jf.fileno())
            try:
                shutil.move(lp(src), lp(d))
                moved[src] = d
            except OSError as e:
                failed += 1
                if failed < 10:
                    print(f"  FAILED {src}: {e}")

    rows = []
    with open(MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if r and r[0] in moved:
                r[0] = moved[r[0]]
            rows.append(r)
    tmp = MANIFEST + ".new"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, MANIFEST)

    print(f"\nmoved {len(moved):,} files, {failed} failures; manifest updated")
    print(f"journal: {JOURNAL}")

    # what is left behind is the honest remainder
    left = 0
    for root in (LIB, NODATE):
        for dp, _, fns in os.walk(root):
            left += len(fns)
    print(f"\n{left:,} files remain in Library\\ and NoDate\\ - unassigned origins, "
          f"for review")


if __name__ == "__main__":
    main()
