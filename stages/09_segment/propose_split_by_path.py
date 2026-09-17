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

# A DEVICE BELONGS TO A PERSON, NOT TO A YEAR.
#
# Krish reviewed the grouped page on 2026-09-18 and named 30 groups as Communal.
# Five of those devices also appeared in years he had not named - SM-G960F 2019
# (303 files), FE330,X845,C550 2008 (297), SM-G935F 2018 (250) - and a phone does
# not change owner between years. Asked, he confirmed: the whole device is
# Communal, every year. 3,001 files turned on that question, which is why it was
# asked rather than inferred.
#
# Camera models, not people's names: nothing here identifies anybody.
COMMUNAL_DEVICES = {
    "lg-k350n", "redmi note 10 lite", "canon eos 550d", "lumia 535",
    "finepix hs30exr", "fe330,x845,c550", "fe230/x790", "sm-g935f",
    "sm-g960f", "iphone 16 pro max", "iphone 17 pro max", "hero9 black",
    "dcr-pc120e",
}
# SM-G986B (1,231 files, 2021) is deliberately NOT here. It is a Samsung like
# two of the models above, and he did not name it - so it stays Personal.

# The scanned family libraries, which name themselves in the filename. He named
# three years of these and the same device answer applies: all of them.
SCANNED = "old photo"

# Files with NO camera at all, sitting in Pending-Segmentation. These are year
# buckets rather than a device, so naming some years and not others is coherent -
# he judged them on their photographs. Only these three are Communal; the other
# nine (1,759 files) are a separate page he asked to see.
COMMUNAL_NOCAM_YEARS = {"2016", "2023", "2024"}


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
    # make, model and year: the device rule needs them, and the first version of
    # this script did not read them at all.
    meta = {h: (mk or "", md or "", yr or "") for h, mk, md, yr in db.execute(
        "select hash, make, model, year from files where hash is not null")}
    db.close()
    print("files in the index: {:,}".format(len(rows)))
    print("Communal devices  : {}".format(len(COMMUNAL_DEVICES)))

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
        base = os.path.basename(low)
        make, model, year = meta.get(h, ("", "", ""))
        queue_name = QUEUE.search(p).group(1).lower()

        # In order: a path signal, then the device, then the scanned libraries,
        # then the three no-camera years he named. Everything else is Personal.
        hit = next((s for s in signals if s in low), "")
        if not hit and model.strip().lower() in COMMUNAL_DEVICES:
            hit = "device: " + model.strip()
        if not hit and SCANNED in base:
            hit = "scanned family photos"
        if (not hit and not model.strip()
                and queue_name == "pending-segmentation"
                and year in COMMUNAL_NOCAM_YEARS):
            hit = "no camera, " + year
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

    # TMP + RENAME, and never throw the work away on a locked target.
    #
    # This run took 164 seconds and then died with PermissionError, because the
    # CSV was open in Excel - I had opened it myself for Krish to review. The
    # same shape as the index promote: a reader holding the destination is not a
    # reason to lose a finished result (learning 55 - a traceback on the last
    # line of a long job reads as "the work is gone" when the work is right
    # there).
    tmp = a.out + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Side", "Signal", "Queue", "Kind",
                                           "Hash", "Source", "Destination"])
        w.writeheader()
        w.writerows(out)
    print()
    try:
        os.replace(tmp, a.out)
        print("wrote {} - {:,} proposed moves".format(a.out, len(out)))
    except PermissionError:
        alt = a.out.replace(".csv", ".new.csv")
        try:
            os.replace(tmp, alt)
        except PermissionError:
            alt = tmp
        print("COULD NOT REPLACE {}".format(a.out))
        print("  Something holds it open - Excel, most likely, because the")
        print("  review page and this CSV are both opened for you to look at.")
        print("  NOTHING IS LOST: the finished proposal is at")
        print("    {}".format(alt))
        print("  Close the file and rename it, or re-run.")
    print("NOTHING HAS MOVED. Review it, then apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
