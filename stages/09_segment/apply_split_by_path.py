r"""Apply an approved per-file split. Journalled, collision-refusing, reversible.

    python apply_split_by_path.py                          # dry run
    python apply_split_by_path.py --apply
    python apply_split_by_path.py --verify
    python apply_split_by_path.py --reverse <journal>

Krish approved the proposal on 2026-09-18 after reviewing it as groups of
photographs: *"split review doc looks good to me"*. 18,985 files move -
8,372 to `Media\Communal`, 10,613 to `Media\Personal`.

WHY NOT apply_split.py

That one joins `ORIGIN-MAP.csv` to `SPLIT-PROPOSAL.csv` by origin folder - which
12,901 of these files do not have - and builds destinations from the
PRE-MIGRATION layout (`LIBROOT\Library\...`, `LIBROOT\NoDate\...`) that
`migrate_layout.py` restructured away. Every path it computes is wrong. It is
marked STALE in STAGE.md.

WHY IT REUSES sweep_intimate

`sweep_intimate.reverse()` reads only the `source` and `destination` columns, and
`tests/test_segment_moves.py` already watches it put every file back and REFUSE
when a source name has been taken. So this writes a journal with those same
columns and imports that function rather than writing a second one: two copies of
a move engine is exactly how `side_of` ended up defined twice in two files.

THE THREE RULES, same as the intimate sweep

1. The journal is written BEFORE anything moves, so a process killed mid-move
   can still be reversed.
2. A destination that already exists, or that two sources both want, STOPS the
   run. 18,985 files share plenty of basenames.
3. `--verify` re-derives every side from the FILESYSTEM afterwards, never from
   the plan.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import os
import shutil
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from sides import side_of                                        # noqa: E402
from sweep_intimate import lp, reverse                           # noqa: E402

PROPOSAL = os.path.join(P.AUDIT, "SPLIT-FINAL.csv")
FIELDS = ["when", "hash", "side", "signal", "source", "destination"]


def load(proposal):
    rows = []
    with io.open(proposal, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({"when": dt.datetime.now().isoformat(timespec="seconds"),
                         "hash": r.get("Hash", ""), "side": r["Side"],
                         "signal": r.get("Signal", ""),
                         "source": r["Source"], "destination": r["Destination"]})
    return rows


def same_bytes(a, b, chunk=1 << 20):
    """Identical content, by bytes - not by name, size, or hope."""
    try:
        if os.path.getsize(lp(a)) != os.path.getsize(lp(b)):
            return False
        ha, hb = hashlib.blake2b(digest_size=16), hashlib.blake2b(digest_size=16)
        with open(lp(a), "rb") as fa, open(lp(b), "rb") as fb:
            while True:
                x, y = fa.read(chunk), fb.read(chunk)
                if not x and not y:
                    break
                ha.update(x)
                hb.update(y)
        return ha.hexdigest() == hb.hexdigest()
    except OSError:
        return False


def free_name(dest):
    r"""`x.jpg` -> `x__2.jpg`, `x__3.jpg` ... until one is free.

    Probed rather than assumed: a single `__2` would itself collide the second
    time a name repeats, which is exactly how an overwrite gets introduced by a
    fix for overwrites.
    """
    stem, ext = os.path.splitext(dest)
    n = 2
    while os.path.exists(lp("{}__{}{}".format(stem, n, ext))):
        n += 1
    return "{}__{}{}".format(stem, n, ext)


def resolve_collisions(rows):
    r"""Skip duplicates, rename different photographs, refuse the rest.

    Krish, 2026-09-18, shown 187 collisions - 49 byte-identical duplicates and
    138 different photographs sharing a filename: rename with a suffix, skip the
    duplicates, delete nothing.

    Returns (moves, skipped, renamed, unresolved). `unresolved` keeps the
    refusal alive for the case this CANNOT settle: two sources wanting one
    destination. That is 0 today and must never become a silent overwrite.
    """
    moves, skipped, renamed, unresolved = [], [], [], []
    wanted = {}
    for r in rows:
        key = r["destination"].lower()
        if key in wanted and wanted[key] != r["source"]:
            unresolved.append((wanted[key], r["source"], r["destination"]))
            continue
        wanted[key] = r["source"]

        if not os.path.exists(lp(r["destination"])):
            moves.append(r)
            continue
        if same_bytes(r["source"], r["destination"]):
            # An identical copy is already there. Krish chose to leave the
            # source where it is rather than delete it: nothing in this project
            # deletes a photograph to tidy a folder.
            skipped.append(r)
            continue
        r = dict(r, destination=free_name(r["destination"]))
        renamed.append(r)
        moves.append(r)
        wanted[r["destination"].lower()] = r["source"]
    return moves, skipped, renamed, unresolved


def verify(proposal):
    """Re-derive from the filesystem: is anything still sitting in a queue?"""
    rows = load(proposal)
    wrong = []
    for r in rows:
        here = r["destination"] if os.path.exists(lp(r["destination"])) \
            else (r["source"] if os.path.exists(lp(r["source"])) else None)
        if here is None:
            wrong.append((r["source"], "MISSING from both source and destination"))
        elif side_of(here) != r["side"]:
            wrong.append((here, "reads {}, expected {}".format(
                side_of(here), r["side"])))
    print("files checked      : {:,}".format(len(rows)))
    print("not where expected : {:,}".format(len(wrong)))
    for p, why in wrong[:12]:
        print("   {}  {}".format(why, p))
    if not wrong:
        print("every file sits on the side the approved proposal gave it.")
    return len(wrong)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proposal", default=PROPOSAL)
    ap.add_argument("--journal", default=os.path.join(
        P.AUDIT, "split-apply-{}.csv".format(
            dt.datetime.now().strftime("%Y%m%dT%H%M%S"))))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--reverse", default="", metavar="JOURNAL")
    a = ap.parse_args()

    if a.reverse:
        return reverse(a.reverse)
    if not os.path.exists(a.proposal):
        print("STOPPING: no proposal at {}".format(a.proposal))
        print("  Run propose_split_by_path.py, review it with")
        print("  review_split_by_path.py, and only then apply.")
        return 1
    if a.verify:
        return 0 if verify(a.proposal) == 0 else 1

    rows = load(a.proposal)
    by_side = collections.Counter(r["side"] for r in rows)
    print("proposed moves: {:,}".format(len(rows)))
    for s, n in by_side.most_common():
        print("   -> {:<10} {:>7,}".format(s, n))

    gone = [r for r in rows if not os.path.exists(lp(r["source"]))]
    if gone:
        print()
        print("STOPPING: {} source file(s) no longer exist.".format(len(gone)))
        for r in gone[:8]:
            print("   {}".format(r["source"]))
        print("  The proposal is stale - something moved since it was written.")
        print("  Regenerate it rather than moving what is left: a partial plan")
        print("  applied in full is how a library ends up half-sorted.")
        return 1

    moves, skipped, renamed, unresolved = resolve_collisions(rows)
    if unresolved:
        print()
        print("STOPPING: {} clash(es) this cannot settle - two sources want one "
              "destination.".format(len(unresolved)))
        for a_, b_, d_ in unresolved[:8]:
            print("   {}\n   {}\n   both -> {}".format(a_, b_, d_))
        print("  Nothing moved. Renaming one of a pair is a guess about which")
        print("  photograph matters, and that is not mine to make.")
        return 1

    print()
    print("  to move        : {:,}".format(len(moves)))
    print("  skipped, identical copy already at the destination: {:,}".format(
        len(skipped)))
    print("  renamed to avoid overwriting a different photograph: {:,}".format(
        len(renamed)))
    for r in renamed[:4]:
        print("     {} -> {}".format(os.path.basename(r["source"])[:52],
                                     os.path.basename(r["destination"])[:52]))

    if not a.apply:
        print()
        print("no missing sources, no unresolvable clashes.")
        print("dry run - nothing moved. Re-run with --apply.")
        return 0
    rows = moves

    with io.open(a.journal, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print()
    print("journal written FIRST: {}".format(a.journal))

    moved = 0
    for r in rows:
        os.makedirs(os.path.dirname(lp(r["destination"])), exist_ok=True)
        shutil.move(lp(r["source"]), lp(r["destination"]))
        moved += 1
        if moved % 2000 == 0:
            print("   {:,} of {:,}".format(moved, len(rows)))
    print("moved {:,} of {:,}".format(moved, len(rows)))
    print()
    print("Now: python stages/08_index/build_db.py   (18,985 paths changed)")
    print("Then: apply_split_by_path.py --verify")
    print("To undo: apply_split_by_path.py --reverse {}".format(a.journal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
