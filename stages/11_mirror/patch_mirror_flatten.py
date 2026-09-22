r"""Repoint the mirror journal at the paths the flatten left behind.

    python patch_mirror_flatten.py            # report, writes nothing
    python patch_mirror_flatten.py --apply
    python patch_mirror_flatten.py --verify

WHY THIS EXISTS

`flatten_months.py` collapsed `YYYY\YYYY-MM\` to `YYYY\` on BOTH copies on
2026-09-21, moving 66,047 files on each. It journalled every move, and
`patch_inventory_moves.py` repointed the inventory records so nothing had to
re-walk 82,000 files. The MIRROR journal was not in that list.

So `h-mirror.csv` still describes a library that no longer exists. Every one of
its 66,113 affected rows names a source under `YYYY\YYYY-MM\` that is gone and
a destination on H: that is equally gone, while both files sit one level up,
untouched and already uploaded. `mirror_to_h.py --status` reads that and says
**66,047 files still to send** - of a library that is completely mirrored and
was proven file-by-file against Google's own md5 on 2026-09-19.

THE COST OF NOT DOING THIS IS NOT THE UPLOAD

The uploader would not actually re-send them: it finds the destination present
at the right size and writes `already-present`. That is the damage. Those
66,113 rows currently carry `written` with the blake2b AND md5 computed on the
bytes as they were written - the only evidence in this project that crosses the
network boundary in the right direction, and the evidence `verify_drive_md5.py`
matched against Google's checksums. `already-present` carries no digest at all,
because it is a SIZE check on a mount, and size is not content (learning 7,
learning 22). Letting the uploader "fix" the staleness would silently trade the
proof for a size comparison against a local cache - precisely the illusion this
stage's docstring says cost somebody 140.62 GB of verification proven by
nothing.

So the digests are kept and the paths are corrected underneath them.

THE REFUSAL THAT MATTERS

A row is only repointed when BOTH sides move together: its source appears in
the D: flatten journal AND its destination appears in the H: one. A row whose
source flattened but whose destination did not means the two copies diverged,
and rewriting one side of it would produce a journal claiming a file is
mirrored at a path where nothing is. Those are counted and left alone, never
guessed at.

The two journals disagree about their own column names - the D: one writes
`source,destination` and the H: one `From,To` (learning 67, found the hard way
when a reader read columns the writer never wrote). Both spellings are accepted
here, and a journal carrying neither stops the run rather than silently mapping
nothing, because a map that comes back empty looks exactly like a library that
needs no patching.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import random
import shutil
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                               # noqa: E402

JOURNAL = os.path.join(P.AUDIT, "h-mirror.csv")
FLAT_D = os.path.join(P.AUDIT, "FLATTEN-MOVES-d--contentlibrary-media.csv")
FLAT_H = os.path.join(P.AUDIT, "FLATTEN-MOVES-h--my-drive-contentlibrary-media.csv")

# Either spelling, because the two journals were written with different ones.
SRC_KEYS = ("source", "From", "from", "Source")
DST_KEYS = ("destination", "To", "to", "Destination")


def first(row, keys):
    for k in keys:
        if k in row and row[k]:
            return row[k]
    return ""


def load_moves(path):
    r"""source -> destination, lowercased key. Empty is an error, not a result."""
    if not os.path.exists(path):
        sys.exit("no flatten journal at {}\n"
                 "  Without it nothing can be repointed, and an empty map is\n"
                 "  indistinguishable from a library that needs no patch."
                 .format(path))
    out = {}
    with io.open(path, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        for r in rd:
            s, d = first(r, SRC_KEYS), first(r, DST_KEYS)
            if s and d:
                out[s.lower()] = d
        names = rd.fieldnames
    if not out:
        sys.exit("{} parsed to 0 moves - its columns are {}, and this reader\n"
                 "  knows {} / {}. Refusing to report 'nothing to patch'."
                 .format(path, names, SRC_KEYS, DST_KEYS))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=JOURNAL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--sample", type=int, default=200,
                    help="how many patched rows --verify stats on the mount. "
                         "A stat does not hydrate a placeholder; reading the "
                         "bytes would (learning 5), so this never opens a file.")
    a = ap.parse_args()

    dmap, hmap = load_moves(FLAT_D), load_moves(FLAT_H)
    print("flatten journals : D: {:,} moves   H: {:,} moves".format(len(dmap), len(hmap)))

    with io.open(a.journal, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        fields = rd.fieldnames
        rows = list(rd)
    print("mirror journal   : {:,} rows".format(len(rows)))

    patched = split = untouched = 0
    out_rows, patched_rows = [], []
    for r in rows:
        s_new = dmap.get((r.get("source") or "").lower())
        d_new = hmap.get((r.get("dest") or "").lower())
        if s_new and d_new:
            r = dict(r)
            r["source"], r["dest"] = s_new, d_new
            patched += 1
            patched_rows.append(r)
        elif s_new or d_new:
            # One side moved and the other did not. The copies disagree; a
            # guess here writes a journal that lies about where a file is.
            split += 1
        else:
            untouched += 1
        out_rows.append(r)

    print("rows repointed   : {:,}".format(patched))
    print("rows left alone  : {:,}".format(untouched))
    print("ONE-SIDED (refused): {:,}".format(split))
    if split:
        print("  these name a file that moved on one copy and not the other.")
        print("  They are NOT patched. Look at them before trusting the mirror.")

    if a.verify:
        # Sample only the rows this tool CHANGED. The untouched rows include
        # `_Review\` and `Archive\`, which Krish emptied on 2026-09-21 - 7,678
        # files removed from both copies and journalled in
        # MIRROR-DELETIONS-APPLIED.csv. Those rows correctly describe files that
        # no longer exist anywhere, and counting them as verification failures
        # would report a fault that is actually a completed instruction.
        cand = [r for r in patched_rows if r.get("outcome") == "written"]
        pick = random.sample(cand, min(a.sample, len(cand)))
        miss_src = [r for r in pick if not os.path.exists(r["source"])]
        # Plain paths on the mount, never \\?\ (learning 59).
        miss_dst = [r for r in pick if not os.path.exists(r["dest"])]
        print()
        print("verify sample    : {:,} of the {:,} REPOINTED rows".format(
            len(pick), patched))
        print("  source missing on D:: {:,}".format(len(miss_src)))
        print("  dest   missing on H:: {:,}".format(len(miss_dst)))
        for r in (miss_src + miss_dst)[:5]:
            print("    {}".format(r["source"]))
        if miss_src or miss_dst:
            return 1

    if not a.apply:
        print()
        print("REPORT ONLY - nothing written. Re-run with --apply.")
        return 0
    if not patched:
        print()
        print("nothing to patch")
        return 0

    backup = a.journal + ".preflatten"
    if not os.path.exists(backup):
        shutil.copy2(a.journal, backup)
        print()
        print("backed up the journal as it stood -> {}".format(backup))
    else:
        print()
        print("{} already exists, keeping the ORIGINAL backup".format(backup))

    tmp = a.journal + ".new"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, a.journal)
    print("APPLIED: {:,} rows repointed in {}".format(patched, a.journal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
