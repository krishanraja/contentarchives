r"""Rewrite moved paths in the inventory from a move journal. Seconds, not an hour.

    python patch_inventory_moves.py --from INVENTORY.csv.backup \
        --journal split-apply-*.csv --journal intimate-sweep-*.csv
    python patch_inventory_moves.py ... --apply

WHY THIS EXISTS

`build_inventory.py` walks the whole library and rewrites INVENTORY.csv in
place. On 2026-09-17 that was killed TWICE by the system running low on memory -
once with --video and once without, so ffprobe was never the cause - and because
it truncates as it goes, a complete 82,193-row inventory became a 21,076-row
corpse. The complete one from 12 September survived only because it had been
copied aside.

But a full walk is the wrong instrument anyway. After a move, the ONLY thing
wrong with the inventory is the `LibraryPath` column of the files that moved,
and every mover in stage 09 writes a journal of exactly `source -> destination`.
Patching those rows is exact, costs seconds, uses constant memory, and preserves
every EXIF and duration value the walk would have recomputed - or, in the
photo-only case, silently discarded for 12,963 videos.

WHAT IT REFUSES TO DO

- Work in place. It writes a temp file and promotes it only after verification,
  because this project has already lost one record to a careless in-place write.
- Guess. A journal row whose source is not in the inventory is REPORTED, not
  quietly skipped: that means the two records disagree, and a patch applied over
  a disagreement is how a library ends up subtly wrong rather than obviously
  broken.
- Claim success. `--verify` checks every patched path against the FILESYSTEM,
  because the inventory is a claim about the disk and the disk is the truth.
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import io
import os
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from sides import side_of                                        # noqa: E402

OUT = os.path.join(P.AUDIT, "INVENTORY.csv")


def lp(p):
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def load_moves(patterns):
    """source (lowercased) -> destination, from every journal given."""
    moves, files = {}, []
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            files.append(path)
            with io.open(path, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    s, d = r.get("source"), r.get("destination")
                    if s and d:
                        moves[s.lower()] = d
    return moves, files


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True,
                    help="a COMPLETE inventory to patch - never the live one "
                         "while it is being read")
    ap.add_argument("--journal", action="append", default=[],
                    help="move journal(s); globs allowed, repeatable")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.src):
        print("STOPPING: no inventory at {}".format(a.src))
        return 1
    if not a.journal:
        print("STOPPING: no --journal given. Patching nothing and calling it")
        print("  done would leave the inventory looking refreshed.")
        return 1

    moves, journals = load_moves(a.journal)
    print("journals: {}".format(", ".join(os.path.basename(j) for j in journals)))
    print("moves   : {:,}".format(len(moves)))
    if not moves:
        print("STOPPING: the journals hold no moves.")
        return 1

    tmp = a.out + ".tmp"
    patched = missing = rows = 0
    seen_sources = set()
    sides = collections.Counter()
    with io.open(a.src, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        try:
            col = header.index("LibraryPath")
        except ValueError:
            print("STOPPING: {} has no LibraryPath column".format(a.src))
            return 1
        with io.open(tmp, "w", encoding="utf-8", newline="") as out:
            w = csv.writer(out)
            w.writerow(header)
            for row in reader:
                rows += 1
                if len(row) > col:
                    dest = moves.get(row[col].lower())
                    if dest:
                        seen_sources.add(row[col].lower())
                        row[col] = dest
                        patched += 1
                    sides[side_of(row[col])] += 1
                w.writerow(row)

    print()
    print("rows read    : {:,}".format(rows))
    print("paths patched: {:,}".format(patched))

    # A journal row whose source is not in the inventory means the two records
    # disagree. Reported, never skipped quietly.
    unmatched = [s for s in moves if s not in seen_sources]
    if unmatched:
        print("journal moves with NO matching inventory row: {:,}".format(
            len(unmatched)))
        for s in unmatched[:6]:
            print("   {}".format(s[-90:]))

    print()
    print("=== sides in the patched inventory ===")
    for s, n in sides.most_common():
        print("  {:<12} {:>8,}".format(s, n))

    # VERIFY AGAINST THE DISK, not against the plan.
    print()
    print("=== every patched path checked against the FILESYSTEM ===")
    gone = [d for d in moves.values() if not os.path.exists(lp(d))]
    print("  destinations that do not exist: {:,}".format(len(gone)))
    for d in gone[:6]:
        print("     {}".format(d[-90:]))

    if gone:
        print()
        print("STOPPING: the journal names destinations that are not on disk.")
        print("  Promoting this would make the inventory disagree with the")
        print("  library it describes. Nothing written.")
        os.remove(tmp)
        return 1

    if not a.apply:
        print()
        print("dry run - wrote nothing. Re-run with --apply to promote.")
        os.remove(tmp)
        return 0

    os.replace(tmp, a.out)
    print()
    print("promoted {} ({:,} rows)".format(a.out, rows))
    print("Now: python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
