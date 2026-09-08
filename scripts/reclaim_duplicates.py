r"""Reclaim byte-identical duplicates the stale-index bug let into the library.

WHAT HAPPENED

apply_split.py moved tens of thousands of files out of `Library\` into
`Personal\` and `Communal\`. The dedup index caches PATHS and is refreshed only
from autopilot-added.csv, which records additions - a move is neither an
addition nor recorded. The index went 62.9% stale.

A dedup candidate that will not open hashes to None. `None == th` is False. So
every Takeout member whose only candidate was a stale path was filed as NEW,
silently. 35,114 members were checked; 382 were caught. The library gained
roughly 222 GB of byte-identical duplicates and nothing errored.

WHICH COPY DIES

The `Library\` copy. `Personal\` and `Communal\` hold files that have already
been dated, split and reviewed; `Library\` is the unassigned staging area where
fresh ingest lands. Deleting the staged copy keeps the organised one and leaves
the chronology untouched.

Where BOTH copies are in `Library\`, the one with the longer name goes - those
are the `__1` suffixes the placement adds on collision.

SAFETY

Every deletion goes through guarded_delete.delete_with_surviving_copy, which
re-verifies from the filesystem at the moment of the unlink: both paths present,
DIFFERENT INODES, equal size, identical blake2b-256, survivor readable to its
last byte. Nothing here is trusted to the scan that found it - the scan is only
a shortlist, and by the time it is acted on the library has moved on.

A pair that fails any check is skipped and reported. There is no override.

    python reclaim_duplicates.py             # scan and report
    python reclaim_duplicates.py --apply
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guarded_delete import delete_with_surviving_copy, DeletionRefused  # noqa: E402

LIB = r"D:\PhotoLibrary"
STAGING = os.path.join(LIB, "Library")


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def qhash(path: str, size: int) -> str:
    """head+tail signature - cheap shortlist, never the basis for a deletion."""
    h = hashlib.blake2b(digest_size=16)
    with open(lp(path), "rb") as f:
        h.update(f.read(1024 * 1024))
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)
            h.update(f.read())
    return h.hexdigest()


def victim_and_survivor(paths: list[str]) -> tuple[str, str] | None:
    staged = [p for p in paths if p.lower().startswith(STAGING.lower() + os.sep)]
    settled = [p for p in paths if p not in staged]
    if settled and staged:
        return staged[0], settled[0]
    if len(staged) > 1:                      # both in staging: drop the __1 suffix copy
        s = sorted(staged, key=lambda p: (len(os.path.basename(p)), p))
        return s[-1], s[0]
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-size", type=int, default=64 * 1024)
    a = ap.parse_args()

    print("indexing the library by size...")
    bysize: dict[int, list] = collections.defaultdict(list)
    for dp, dns, fns in os.walk(LIB):
        if "_Catalog" in dp:
            continue
        for f in fns:
            p = os.path.join(dp, f)
            try:
                st = os.stat(lp(p))
            except OSError:
                continue
            if st.st_size >= a.min_size:
                bysize[st.st_size].append((p, st.st_ino))

    groups = [(s, v) for s, v in bysize.items() if len({i for _, i in v}) > 1]
    print(f"  {len(groups):,} size groups holding more than one inode")

    # A long scan that prints nothing is indistinguishable from a hang, and
    # the difference matters when the alternative is killing it and losing
    # 30 minutes of hashing. Report often enough to be believed.
    pairs, freed_est = [], 0
    for gi, (size, items) in enumerate(groups, 1):
        if gi % 500 == 0:
            print(f"  {gi:,}/{len(groups):,} groups, {len(pairs):,} pairs, "
                  f"{freed_est/1024**3:.1f} GB so far", flush=True)
        perino: dict[int, str] = {}
        for p, i in items:
            perino.setdefault(i, p)
        bysig: dict[str, list[str]] = collections.defaultdict(list)
        for i, p in perino.items():
            try:
                bysig[qhash(p, size)].append(p)
            except OSError:
                continue
        for _, paths in bysig.items():
            if len(paths) < 2:
                continue
            vs = victim_and_survivor(paths)
            if not vs:
                continue
            pairs.append((vs[0], vs[1], size))
            freed_est += size

    GB = 1024 ** 3
    print(f"\n  candidate pairs : {len(pairs):,}")
    print(f"  reclaim estimate: {freed_est/GB:.1f} GB")
    staged = sum(1 for v, _, _ in pairs if v.lower().startswith(STAGING.lower() + os.sep))
    print(f"  of which the deleted copy is in Library\\ (staging): {staged:,}")

    if not a.apply:
        print("\nDRY RUN. Every pair is re-verified by content at deletion time;")
        print("this list is only a shortlist. Re-run with --apply.")
        return

    freed = deleted = refused = 0
    reasons: collections.Counter = collections.Counter()
    for victim, survivor, _size in pairs:
        try:
            freed += delete_with_surviving_copy(
                victim, survivor,
                "user-directed: byte-identical duplicate admitted by the stale "
                "library index; the settled copy is kept")
            deleted += 1
        except DeletionRefused as e:
            refused += 1
            reasons[str(e).split(":")[0][:60]] += 1
        if deleted and deleted % 2000 == 0:
            print(f"  {deleted:,} deleted, {freed/GB:.1f} GB", flush=True)

    print(f"\ndeleted {deleted:,}, freed {freed/GB:.2f} GB, refused {refused:,}")
    for r, n in reasons.most_common(8):
        print(f"    {n:>6}  {r}")


if __name__ == "__main__":
    main()
