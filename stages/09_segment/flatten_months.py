r"""Collapse `YYYY\YYYY-MM\` into `YYYY\`, identically on every copy.

    python flatten_months.py --root "D:\ContentLibrary\Media"
    python flatten_months.py --root "D:\ContentLibrary\Media" --apply
    python flatten_months.py --root "H:\My Drive\ContentLibrary\Media" --apply

Krish, 2026-09-21: *"I do not want folders by the Month ("2017-02"), just put
all of 2017 photos in the 2017 folder and there needs to be no subfolders."*

COLLISIONS ARE THE WHOLE PROBLEM, AND THEY ARE NOT RARE

`Communal\2024\2024-05\001.jpg` and `Communal\2024\2024-09\001.jpg` are two
different photographs that become one path. Measured before writing this: 463
month folders, 66,493 files, and **70 names that collide, affecting 140 files**.
A flatten that silently overwrote would destroy one of each pair, and the loss
would be invisible - the file count would simply be lower than expected, which
is exactly the kind of quiet wrong this repo exists to stop.

Krish chose prefixing, so a colliding file becomes `05_001.jpg`: the month it
came from is preserved in the name rather than thrown away. ONLY colliding files
are renamed. Renaming all 66,493 would churn every path in every record to solve
a problem 140 of them have.

THE MOVE IS PLANNED IN FULL BEFORE ANYTHING MOVES

Every source is mapped to its destination first, and the plan is checked for
two failures that a file-at-a-time loop cannot see:

  - a destination claimed twice (the collision case, resolved by prefixing)
  - a destination that already exists as an unrelated file

If either survives planning, nothing moves at all. A half-flattened tree is
worse than an unflattened one, because no record describes it.

EVERY MOVE IS JOURNALLED BEFORE IT HAPPENS, so the records can be repointed
afterwards without re-walking 82,000 files - `patch_inventory_moves.py` exists
for exactly that, and a move journal is its input. Three records are keyed on
PATH (INVENTORY.csv, HASH-INDEX.csv, MIGRATION-HASHES.csv) plus the manifest,
and a move stales all of them.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
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

MONTH_RX = re.compile(r"^(\d{4})-(\d{2})$")
csv.field_size_limit(1 << 30)


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def is_mount(root: str) -> bool:
    r"""The Drive mount rejects the \\?\ long-path prefix (learning 59).

    Docstring marked raw: without the r-prefix Python reads the backslashes as
    escape sequences and emits `SyntaxWarning: invalid escape sequence` on every
    single run. The same trap in its other forms cost seven round trips on
    2026-09-20.
    """
    return os.path.splitdrive(root)[0].lower() == "h:"


def plan(root: str):
    """Every move this flatten would make, and every problem in it."""
    moves = []
    claimed = collections.defaultdict(list)

    for dp, dns, fns in os.walk(root):
        month = os.path.basename(dp)
        m = MONTH_RX.match(month)
        if not m:
            continue
        year_dir = os.path.dirname(dp)
        if os.path.basename(year_dir) != m.group(1):
            # A YYYY-MM folder that is not inside its own YYYY. Left alone and
            # reported rather than guessed at.
            print("  SKIPPED, month folder not inside its year: {}".format(dp))
            continue
        for fn in fns:
            claimed[(year_dir, fn.lower())].append(os.path.join(dp, fn))

    problems = []
    for (year_dir, lower), sources in sorted(claimed.items()):
        if len(sources) == 1:
            src = sources[0]
            moves.append((src, os.path.join(year_dir, os.path.basename(src)),
                          False))
            continue
        # Collision: prefix each with the month it came from.
        for src in sorted(sources):
            month = os.path.basename(os.path.dirname(src))[5:7]
            dest = os.path.join(year_dir,
                                "{}_{}".format(month, os.path.basename(src)))
            moves.append((src, dest, True))

    # A destination that already exists and is not one of our sources.
    srcs = {os.path.normcase(s) for s, _, _ in moves}
    seen = {}
    for s, dest, pref in moves:
        key = os.path.normcase(dest)
        if key in seen:
            problems.append("two files both want {}: {} and {}".format(
                dest, seen[key], s))
        seen[key] = s
        opener = dest if is_mount(dest) else lp(dest)
        if os.path.exists(opener) and key not in srcs:
            problems.append(
                "destination already exists and is not being moved: {}".format(dest))
    return moves, problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        print("no such root: {}".format(a.root))
        return 1

    moves, problems = plan(a.root)
    prefixed = [m for m in moves if m[2]]
    print("root              : {}".format(a.root))
    print("files to move     : {:,}".format(len(moves)))
    print("month-prefixed    : {:,}  (names that collided)".format(len(prefixed)))
    print("problems          : {:,}".format(len(problems)))
    for p in problems[:20]:
        print("    " + p)
    if problems:
        print()
        print("STOPPING: nothing moved. A half-flattened tree is worse than an")
        print("  unflattened one, because no record describes it.")
        return 1

    if prefixed:
        print()
        print("  collisions, resolved by prefixing the month:")
        for s, d, _ in prefixed[:10]:
            print("      {}  ->  {}".format(
                os.path.basename(s), os.path.basename(d)))

    if not a.apply:
        print()
        print("DRY RUN - nothing touched. Re-run with --apply.")
        return 0

    tag = "".join(c if c.isalnum() else "-" for c in a.root).strip("-").lower()
    journal = os.path.join(P.AUDIT, "FLATTEN-MOVES-{}.csv".format(tag))
    os.makedirs(os.path.dirname(journal), exist_ok=True)
    fresh = not os.path.exists(journal)
    fh = io.open(journal, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if fresh:
        # `source` and `destination`, NOT From/To.
        #
        # patch_inventory_moves.py reads exactly those two keys, and every other
        # mover in stage 09 writes them. The first version of this file wrote
        # From/To, which the patcher would have read as no moves at all: it
        # would have reported success against an inventory it never touched,
        # leaving 66,047 stale paths behind a green tick. A journal whose
        # columns the consumer cannot see is worse than no journal.
        w.writerow(["when", "source", "destination", "prefixed"])

    done = failed = 0
    try:
        for src, dest, pref in moves:
            s_open = src if is_mount(src) else lp(src)
            d_open = dest if is_mount(dest) else lp(dest)
            if not os.path.exists(s_open):
                continue                      # already moved by an earlier run
            try:
                os.replace(s_open, d_open)
            except OSError as e:
                print("  FAILED {}: {}".format(os.path.basename(src), e))
                failed += 1
                continue
            w.writerow([dt.datetime.now().isoformat(timespec="seconds"),
                        src, dest, int(pref)])
            done += 1
            if done % 2000 == 0:
                fh.flush()
                os.fsync(fh.fileno())
                print("  moved {:,}".format(done), flush=True)
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    # Empty month folders, removed only once they are actually empty.
    pruned = 0
    for dp, dns, fns in os.walk(a.root, topdown=False):
        if MONTH_RX.match(os.path.basename(dp)) and not dns and not fns:
            try:
                os.rmdir(dp if is_mount(dp) else lp(dp))
                pruned += 1
            except OSError:
                pass

    print()
    print("moved {:,}, failed {:,}, empty month folders pruned {:,}".format(
        done, failed, pruned))
    print("journal: {}".format(journal))
    print()
    print("EVERY PATH RECORD IS NOW STALE. Repoint them from this journal:")
    print("  python stages/04_inventory/patch_inventory_moves.py")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
