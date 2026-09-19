r"""Copy the irreplaceable camera originals into one tree, ready to ingest.

    python stage_missing_personal.py            # report
    python stage_missing_personal.py --apply

The 669 files that exist ONLY outside the library are scattered across E:, G:,
OneDrive and H:, in folders that mean nothing to the library. `ingest_tree.py`
takes a ROOT, so they have to be gathered first.

WHAT IS TAKEN, AND WHAT IS NOT

`MISSING-PERSONAL-SET.csv` holds every distinct missing file. This takes only
the CAMERA ORIGINALS. Krish, 2026-09-19, ruled on the rest: the
`Loz_Video_Package` renders and the podcast recording are to be DELETED rather
than ingested, so they are deliberately excluded here and named in the output
rather than silently dropped.

RELATIVE STRUCTURE IS PRESERVED, because dating depends on it. `ingest_tree.py`
dates from EXIF first, then the filename, then the FOLDER. A flat copy would
strip the last of those, and VHS and album material with no EXIF lands in
`NoDate\` and stays there. Each file keeps a path under a tag naming the source
it came from.

COPIES, NEVER MOVES. The originals stay where they are until the ingest has
been verified. A move would make this step irreversible before anything had
proven it worked, and the sources are about to be purged on the strength of it.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402

SRC = os.path.join(P.AUDIT, "MISSING-PERSONAL-SET.csv")
STAGE = r"D:\_Staging\missing-personal"
JOURNAL = os.path.join(P.AUDIT, "MISSING-PERSONAL-STAGED.csv")

csv.field_size_limit(1 << 30)

# Krish's ruling: delete, do not ingest.
EXCLUDE = ("loz_video_package", "lozzy mems", "podcast")
# Not content at all.
SCRATCH = ("igexport", "\\debugging\\", "inspiration")


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def source_tag(path: str) -> str:
    low = path.lower()
    if low.startswith("e:"):
        return "from-E"
    if low.startswith("g:"):
        return "from-G"
    if low.startswith("h:"):
        return "from-H"
    if "onedrive" in low:
        return "from-OneDrive"
    return "from-other"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(SRC):
        print("run missing_personal_set.py first - {} is missing".format(SRC))
        return 1

    take, excluded, scratch = [], [], []
    for r in csv.DictReader(io.open(SRC, encoding="utf-8", newline="")):
        p = r["BestPath"]
        low = p.lower()
        try:
            size = int(r["Bytes"] or 0)
        except ValueError:
            size = 0
        if any(f in low for f in EXCLUDE):
            excluded.append((size, p))
        elif any(f in low for f in SCRATCH):
            scratch.append((size, p))
        else:
            take.append((size, p, r["Hash"]))

    print("camera originals to stage : {:>5,}  {:>8.3f} GB".format(
        len(take), sum(t[0] for t in take) / (1 << 30)))
    print("excluded - Krish said DELETE, not ingest:")
    print("    production/podcast    : {:>5,}  {:>8.3f} GB".format(
        len(excluded), sum(s for s, _ in excluded) / (1 << 30)))
    print("    reference/scratch     : {:>5,}  {:>8.3f} GB".format(
        len(scratch), sum(s for s, _ in scratch) / (1 << 30)))
    print()

    by_tag = {}
    for size, p, h in take:
        by_tag[source_tag(p)] = by_tag.get(source_tag(p), 0) + 1
    print("by source: {}".format(by_tag))
    print()

    if not a.apply:
        print("DRY RUN. --apply to copy into {}".format(STAGE))
        return 0

    os.makedirs(lp(STAGE), exist_ok=True)
    copied = failed = 0
    rows = []
    for size, p, h in take:
        tag = source_tag(p)
        drive, rest = os.path.splitdrive(p)
        rel = rest.lstrip("\\/")
        dest = os.path.join(STAGE, tag, rel)
        try:
            os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
            shutil.copy2(lp(p), lp(dest))
            copied += 1
            rows.append([p, dest, size, h])
        except OSError as e:
            failed += 1
            print("  FAILED {}: {}".format(p[-70:], e))
        if copied % 100 == 0 and copied:
            print("  {:,} copied".format(copied), flush=True)

    with io.open(JOURNAL, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Source", "Staged", "Bytes", "Hash"])
        w.writerows(rows)
        fh.flush()
        os.fsync(fh.fileno())

    print()
    print("copied {:,}, failed {:,}".format(copied, failed))
    print("staged at : {}".format(STAGE))
    print("journal   : {}".format(JOURNAL))
    print()
    print("next:")
    print('  python stages/02_ingest/ingest_tree.py --source "{}" \\'.format(STAGE))
    print('      --label missing-personal --apply')
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
