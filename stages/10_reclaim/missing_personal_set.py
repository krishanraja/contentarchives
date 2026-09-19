r"""How many DISTINCT personal files would be lost - and where each one lives.

    python missing_personal_set.py
    python missing_personal_set.py --min-mb 1      # only the substantial ones

Krish wants one number before any source is purged: how much genuinely personal
or communal content exists ONLY outside the library. `unique_personal_media.py`
produces the candidates, but its count OVERSTATES the answer in two ways, and
both have to be removed before the number means anything.

ONE PHOTOGRAPH IN THREE PLACES IS ONE PHOTOGRAPH. `IMG_4666.JPG` sits in E:'s
old library AND in `E:\Pictures\thailand`; `bharti phone upto sept 2019 1507.jpg`
sits on E: AND on G:. Counting the rows counts the copies, not the content. The
library is keyed on content and so is this: files are grouped by hash, and each
group is ONE missing item with a list of the places it survives.

A DOWNLOADED FILM IS NOT A MEMORY. 1.83 GB of the candidate total was a single
pirated Spider-Man film in a `Movies\newpipe` folder. The classifier kept it
because nothing recognised it as noise, which is the right bias - but it must
not be left inflating a figure a purge decision rests on.

WHY HASHES ARE COMPUTED HERE RATHER THAN READ. A UNIQUE verdict reached by the
SIZE GATE never hashed the file - that is the gate's whole value - so most
candidate rows carry an empty Hash. Grouping on (name, size) would be a guess,
and name-plus-size has never been allowed to declare identity in this project
(learnings 22 and 36). The candidate set is small, so it is cheap to settle
properly.

Read-only. Deletes nothing. The output is a review list and a count.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402
from store import content_hash  # noqa: E402

SRC = os.path.join(P.AUDIT, "UNIQUE-PERSONAL-REVIEW.csv")
OUT = os.path.join(P.AUDIT, "MISSING-PERSONAL-SET.csv")

csv.field_size_limit(1 << 30)

# Content that is plainly not a family memory, however it is named. Kept
# separate from unique_personal_media.py's rules so the bias there stays
# towards keeping, and the narrowing happens once, here, in the open.
NOT_A_MEMORY = (
    "\\movies\\", "newpipe", "\\music\\", "\\downloads\\movies",
    "spider-man", "\\torrent", "\\episodes\\", "season ",
)


def is_media_file(path: str) -> bool:
    low = path.lower()
    return not any(frag in low for frag in NOT_A_MEMORY)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-mb", type=float, default=0.0,
                    help="ignore candidates smaller than this")
    a = ap.parse_args()

    if not os.path.exists(SRC):
        print("run unique_personal_media.py first - {} is missing".format(SRC))
        return 1

    rows = []
    for r in csv.DictReader(io.open(SRC, encoding="utf-8", newline="")):
        if r.get("Verdict") != "KEEP-CANDIDATE":
            continue
        try:
            size = int(r.get("Bytes") or 0)
        except ValueError:
            size = 0
        if size < a.min_mb * (1 << 20):
            continue
        rows.append((size, r["Path"]))

    dropped = [(s, p) for s, p in rows if not is_media_file(p)]
    rows = [(s, p) for s, p in rows if is_media_file(p)]

    print("candidates to settle : {:,}  ({:.2f} GB)".format(
        len(rows), sum(s for s, _ in rows) / (1 << 30)))
    if dropped:
        print("set aside as not-a-memory: {:,}  ({:.2f} GB)".format(
            len(dropped), sum(s for s, _ in dropped) / (1 << 30)))
        for s, p in sorted(dropped, reverse=True)[:5]:
            print("    {:>8.1f} MB  {}".format(s / (1 << 20), p[-80:]))
    print()
    print("hashing {:,} file(s) to group copies of the same content...".format(
        len(rows)))

    groups = collections.defaultdict(list)
    unreadable = []
    for i, (size, path) in enumerate(rows, 1):
        try:
            h = content_hash(path)
        except OSError as e:
            unreadable.append((path, str(e)[:80]))
            continue
        groups[h].append((size, path))
        if i % 200 == 0:
            print("  {:,}/{:,}".format(i, len(rows)), flush=True)

    distinct_bytes = sum(v[0][0] for v in groups.values())
    print()
    print("=== WHAT WOULD ACTUALLY BE LOST ===")
    print("  distinct files missing from the library : {:>6,}".format(len(groups)))
    print("  their combined size                     : {:>9.2f} GB".format(
        distinct_bytes / (1 << 30)))
    print("  copies of them scattered across sources : {:>6,}".format(
        sum(len(v) for v in groups.values())))
    if unreadable:
        print("  UNREADABLE (not settled)                : {:>6,}".format(
            len(unreadable)))
        for p, e in unreadable[:5]:
            print("      {}  {}".format(p[-70:], e))

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Hash", "Bytes", "Copies", "BestPath", "AllPaths"])
        for h, v in sorted(groups.items(), key=lambda kv: -kv[1][0][0]):
            v.sort(reverse=True)
            w.writerow([h, v[0][0], len(v), v[0][1],
                        " | ".join(p for _, p in v)])
        fh.flush()
        os.fsync(fh.fileno())
    print()
    print("  one row per missing file: {}".format(OUT))
    print()

    print("the 25 largest, with where each survives:")
    for h, v in sorted(groups.items(), key=lambda kv: -kv[1][0][0])[:25]:
        v.sort(reverse=True)
        print("  {:>8.1f} MB  x{}  {}".format(
            v[0][0] / (1 << 20), len(v), v[0][1][-84:]))

    print()
    print("Ingest these into the library BEFORE purging any source. They are")
    print("the only copies in existence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
