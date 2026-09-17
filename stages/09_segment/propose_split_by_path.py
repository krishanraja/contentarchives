r"""Propose a side for every file in the segmentation queues, by PATH, for review.

    python propose_split_by_path.py                  # writes the proposal, moves nothing
    python propose_split_by_path.py --communal bharti,bhasker,users\raja

Writes `D:\_PhotoAudit\SPLIT-BY-PATH.csv`: one row per FILE, with the side it
would get, the signal that decided it, and the destination it would move to.
It proposes. It never moves anything.

WHY NOT propose_split.py

That one keys on `OriginFolder` from `ORIGIN-MAP.csv`, and **12,901 of the
21,821 unsided files have no origin folder at all**, spanning 1995-2026. It
would silently skip the majority of the job. Its `COMMUNAL` pattern is also
still the retired publisher's pseudonyms - `PERSON-A|PERSON-B|PERSON-C` - so it
matches nothing real and would call everything "personal" or "unclear". It is
marked BROKEN in STAGE.md.

THE RULE, AND WHOSE IT IS

Krish, 2026-09-18: *"anything 'bharti' or 'bhasker' in the folder name in the
pending segmentation is Communal, as is anything from 'Users/Raja'. the rest is
Personal"*, then *"Users/Raja in NoDate is communal, the rest is personal"*.

This is a knowing departure from learning 2 - "folder names are a hint for
review, never a decision" - because the folder handle that makes this stage
tractable does not exist for 59% of the material. He was shown that, and the
departure is recorded in STAGE.md against the invariant it breaks.

He was also told what his own clarification selects: **zero** NoDate files match
`Users\Raja`, so 6,513 of those 6,514 fall through to Personal on no evidence
either way. That is his decision, made with the number in front of him.

WHAT IT REFUSES TO DO

- touch anything already sided: `Media\Personal`, `Media\Communal`, and now
  `Archive\Personal`, `Archive\Communal`, `_Review\Personal`,
  `_Review\Communal` (read by `contentarchives/sides.py`)
- **demote a file that already sits in a Communal folder.** Krish, 2026-09-18:
  never. Somebody put it there; the rule is for material nobody has judged
- leave the other trees: `Archive\99-Unsorted`, `Archive\FromH`, `_Review\Media`
  and `ContentProduction` stay where they are, by his decision - 1,606 files
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from sides import side_of                                        # noqa: E402

OUT = os.path.join(P.AUDIT, "SPLIT-BY-PATH.csv")
# The queues this rule governs, and nothing else.
QUEUE = re.compile(r"\\media\\(pending-segmentation|nodate)\\", re.I)
DEFAULT_COMMUNAL = r"bharti,bhasker,users\raja"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--communal", default=DEFAULT_COMMUNAL,
                    help="comma-separated signals; any in the path means Communal")
    a = ap.parse_args()

    signals = [s.strip().lower() for s in a.communal.split(",") if s.strip()]
    if not signals:
        print("STOPPING: no Communal signals given, so every file would read")
        print("  Personal and the proposal would look like a clean sweep.")
        return 1
    print("Communal signals: {}".format(", ".join(repr(s) for s in signals)))

    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")),
                         uri=True)
    rows = list(db.execute("select path, hash from files"))
    kinds = {h: k for h, k in db.execute(
        "select hash, kind from v_files where hash is not null")}
    db.close()
    print("files in the index: {:,}".format(len(rows)))

    out, counts, sigs = [], collections.Counter(), collections.Counter()
    nonphoto = 0
    for path, h in rows:
        p = path.replace("/", "\\")
        current = side_of(p)
        if current in ("Personal", "Communal"):
            counts["already sided - skipped"] += 1
            continue
        if not QUEUE.search(p):
            counts["another tree - left alone"] += 1
            continue

        low = p.lower()
        hit = next((s for s in signals if s in low), "")
        side = "Communal" if hit else "Personal"
        counts["-> " + side] += 1
        if hit:
            sigs[hit] += 1

        # Preserve the queue below the side, so NoDate stays NoDate: a file with
        # no date does not acquire one by being sided (dating is stage 03's job).
        #
        # Built from guards/paths.py's own constants, NOT from a root this
        # script reassembles. apply_split.py hardcoded `LIBROOT\Library\...` and
        # `LIBROOT\NoDate\...`, migrate_layout.py then restructured the library
        # to Media\<Side>\..., and every destination it computes has been wrong
        # ever since. The constants move with the layout; a local guess does not.
        # (My first attempt here reached for a P.LIBROOT that does not exist.)
        m = QUEUE.search(p)
        queue = m.group(1).lower()
        rel = p[m.end():]
        base = P.PERSONAL if side == "Personal" else P.COMMUNAL
        dest = (os.path.join(base, "NoDate", rel) if queue == "nodate"
                else os.path.join(base, rel))

        kind = kinds.get(h) or ""
        if kind in ("screenshot", "graphic", "document", "meme", "poster"):
            nonphoto += 1
        out.append({"Side": side, "Signal": hit or "(fell through)",
                    "Queue": queue, "Kind": kind, "Hash": h or "",
                    "Source": path, "Destination": dest})

    print()
    for k, n in counts.most_common():
        print("  {:<28} {:>8,}".format(k, n))
    print()
    print("  which signal matched:")
    for s, n in sigs.most_common():
        print("     {:<18} {:>7,}".format(s, n))
    print()
    print("  non-photographs going Personal: {:,} (screenshots, graphics,".format(
        nonphoto))
    print("     documents, memes, posters - sided, and listed for a separate sweep)")

    with io.open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Side", "Signal", "Queue", "Kind",
                                           "Hash", "Source", "Destination"])
        w.writeheader()
        w.writerows(out)
    print()
    print("wrote {} - {:,} proposed moves".format(a.out, len(out)))
    print("NOTHING HAS MOVED. Review it, then apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
