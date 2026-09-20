r"""Delete the library's own duplicate copies, keeping one canonical file each.

    python dedupe_library.py                 # report every decision
    python dedupe_library.py --apply
    python dedupe_library.py --apply --max-seconds 420

Krish, 2026-09-20: *"on the library dedupe, just delete the duplicate
references"*.

1,205 groups of files inside `D:\ContentLibrary` hold byte-identical content -
2,441 files, 20.07 GB reclaimable. Measured, not assumed: every group was
checked for shared inodes first, because two names for one set of bytes free
nothing when one is deleted and the caller who believed it had two copies then
has none in the way that matters (learning 28). None of these are hardlinks.
All 1,205 are genuinely separate copies.

WHY NOT purge_redundant.py OR already_in_library.py

Both refuse anything inside the library, by design and correctly - they exist to
delete OUTSIDE copies that the library makes redundant. This is the opposite
case, so it needs its own tool rather than a weakened version of those.

WHICH COPY SURVIVES, AND WHY IT IS WRITTEN DOWN

A dedupe is only as good as its keeper rule, and a rule nobody can read is a
coin toss with extra steps. Precedence, strongest first:

  1. Media\Personal, Media\Communal  - the curated, sided library. The point of
                                       the whole project.
  2. Media\Pending-Segmentation      - real library content, not yet sided.
  3. Media\ (anything else)
  4. _Review                         - staging for a human decision.
  5. Archive                         - kept, but not the curated copy.
  6. ContentProduction               - working copies made FROM the originals.
                                       8 groups, 14.93 GB: 74% of the reclaim.

Within one rank, a camera-native filename beats an app export - `DJI_2026...`
over `dji_mimo_..._video.mp4` - then the shorter path, then alphabetical. The
tiebreak is deterministic so two runs never disagree about what to keep.

EVERY DELETION GOES THROUGH guarded_delete

Both files re-hashed at the instant of the unlink, a shared inode refused, the
survivor read end-to-end first. A report is never evidence here; this one was
computed minutes ago and is already stale by the time it is acted on.

AFTER THIS RUNS, THE RECORDS ARE STALE. INVENTORY.csv, HASH-INDEX.csv and
MIGRATION-HASHES.csv still name the deleted paths, and `build_db.load_files()`
reads those rather than walking the disk - so the index keeps the dead rows
until they are dropped and it is rebuilt. This prints the exact commands.

AND D: WILL DIVERGE FROM H:. The mirror only ever adds. After this, Drive still
holds the copies the library no longer has. That is a decision for a human, not
a side effect to discover later.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sqlite3
import sys
import time

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402
from guarded_delete import delete_with_surviving_copy, DeletionRefused  # noqa: E402

DB = os.path.join(P.AUDIT, "library.db")
JOURNAL = os.path.join(P.AUDIT, "LIBRARY-DEDUPED.csv")
SEP = chr(92)

csv.field_size_limit(1 << 30)

# Camera-native filenames. An app export carries a second timestamp and a long
# numeric id; the camera's own name is the better keeper.
NATIVE = re.compile(
    r"^(dji_\d|gh\d{6}|gx\d{6}|gopr\d|img[-_]\d|vid[-_]\d|pxl_\d|dsc[fn]?\d|"
    r"mah\d|\d{8}_\d{6})", re.I)


def rank(path: str) -> int:
    p = path.lower()
    if "contentproduction" in p:
        return 6
    if SEP + "archive" + SEP in p:
        return 5
    if "_review" in p:
        return 4
    if "pending-segmentation" in p:
        return 2
    if SEP + "media" + SEP + "personal" + SEP in p or \
       SEP + "media" + SEP + "communal" + SEP in p:
        return 1
    if SEP + "media" + SEP in p:
        return 3
    return 7


def sort_key(path: str):
    base = os.path.basename(path)
    return (rank(path), 0 if NATIVE.match(base) else 1, len(path), path.lower())


def groups_from_index():
    con = sqlite3.connect("file:{}?mode=ro".format(DB.replace("\\", "/")),
                          uri=True)
    try:
        out = []
        for (h,) in con.execute(
                "select hash from files group by hash having count(*) > 1"):
            paths = [p for (p,) in con.execute(
                "select path from files where hash=?", (h,))]
            paths.sort(key=sort_key)
            out.append((h, paths[0], paths[1:]))
        return out
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-seconds", type=float, default=420.0)
    a = ap.parse_args()

    groups = groups_from_index()
    victims = sum(len(v) for _, _, v in groups)
    print("duplicate-content groups : {:,}".format(len(groups)))
    print("copies to remove         : {:,}".format(victims))

    done = set()
    if os.path.exists(JOURNAL):
        for r in csv.DictReader(io.open(JOURNAL, encoding="utf-8", newline="")):
            if r.get("Deleted"):
                done.add(r["Deleted"].lower())
        if done:
            print("resuming, already removed: {:,}".format(len(done)))

    freed_est = 0
    by_rank = {}
    for h, keep, dupes in groups:
        for d in dupes:
            if d.lower() in done:
                continue
            try:
                freed_est += os.path.getsize("\\\\?\\" + d)
            except OSError:
                pass
            by_rank[rank(d)] = by_rank.get(rank(d), 0) + 1
    names = {1: "Media/Personal|Communal", 2: "Pending-Segmentation",
             3: "Media (other)", 4: "_Review", 5: "Archive",
             6: "ContentProduction", 7: "other"}
    print("space to reclaim         : {:.2f} GB".format(freed_est / (1 << 30)))
    print()
    print("what gets deleted, by where it lives:")
    for k in sorted(by_rank):
        print("  {:>6,}  {}".format(by_rank[k], names.get(k, k)))
    print()

    if not a.apply:
        print("a sample of the decisions (KEEP / delete):")
        shown = 0
        for h, keep, dupes in groups:
            if shown >= 12:
                break
            if all(d.lower() in done for d in dupes):
                continue
            print("  KEEP   {}".format(keep[16:104]))
            for d in dupes:
                print("  delete {}".format(d[16:104]))
            shown += 1
        print()
        print("DRY RUN - nothing touched. Re-run with --apply.")
        return 0

    fresh = not os.path.exists(JOURNAL)
    fh = io.open(JOURNAL, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if fresh:
        w.writerow(["Deleted", "Kept", "Bytes", "Hash", "When"])

    t0 = time.time()
    gone = refused = 0
    freed = 0
    reasons = {}
    try:
        for h, keep, dupes in groups:
            if time.time() - t0 > a.max_seconds:
                break
            for d in dupes:
                if d.lower() in done:
                    continue
                try:
                    n = delete_with_surviving_copy(
                        d, keep, "library duplicate; canonical copy kept")
                    freed += n
                    gone += 1
                    w.writerow([d, keep, n, h,
                                time.strftime("%Y-%m-%dT%H:%M:%S")])
                except DeletionRefused as e:
                    refused += 1
                    key = str(e).split(":")[0][:60]
                    reasons[key] = reasons.get(key, 0) + 1
            if (gone + refused) % 100 == 0 and (gone + refused):
                fh.flush()
                os.fsync(fh.fileno())
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    print("removed {:,} copy(ies), freed {:.2f} GB".format(
        gone, freed / (1 << 30)))
    print("refused by the guard: {:,}".format(refused))
    for k, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print("    {:>5,}  {}".format(n, k))
    print()
    print("THE RECORDS ARE NOW STALE. Drop the deleted paths and rebuild:")
    print("  python stages/04_inventory/drop_removed_rows.py --list <paths> --apply")
    print("  python stages/08_index/build_db.py")
    print("  delete D:\\_PhotoAudit\\lib-index.pickle")
    print()
    print("AND D: NOW DIVERGES FROM H:. Drive still holds these copies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
