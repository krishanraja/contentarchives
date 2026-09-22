r"""Hash the library files no hash index has ever seen.

    python hash_new_files.py                # report what is unhashed
    python hash_new_files.py --apply
    python hash_new_files.py --apply --workers 8

WHY THIS EXISTS

The documented chain for new material is `ingest_tree.py --apply`, then
`reconcile_disk.py --write`, then `build_db.py`. Run exactly that and the new
files appear in the index with **no hash**, because nothing in it computes one:
`ingest_tree` hashes only the candidates that collide on size, `reconcile_disk`
appends rows from a directory walk, and `build_db` joins `path -> hash` out of
`HASH-INDEX.csv` and `MIGRATION-HASHES.csv` rather than reading any file.

A row with no hash is not a row with a gap. It is INVISIBLE:

  * `backfill_thumbs.py` drives from the index, so it never looks at it - 11,707
    files newly ingested on 2026-09-22 left it reporting 116 files to do
  * every tag in the enrichment store hangs off the content hash, so the
    classifier has nothing to write against
  * `faces_embed.py` works from thumbnails and frames that were never made
  * the naming games join on hash, so the people in those photographs cannot
    be asked about

`backfill_thumbs.py`'s own docstring already names this exact shape: files are
"not unclassified because they are hard; they are unclassified because nothing
ever looked." That was written about three trees the thumbnailer was never
pointed at. This is the same hole one step earlier in the chain, and it opens
every single time material is ingested.

WHAT IT DOES NOT DO

It does not re-hash anything already indexed, and it never overwrites an
existing hash. `HASH-INDEX.csv` and `MIGRATION-HASHES.csv` are records of what
the bytes were at a moment that can no longer be reproduced - the migration's
own record - and a "refresh" that silently replaced one would destroy the only
evidence a file changed. Appends only, to `HASH-INDEX.csv`, which is the
additive half of the pair.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                               # noqa: E402
from store import content_hash                                  # noqa: E402

INVENTORY = os.path.join(P.AUDIT, "INVENTORY.csv")
HASH_INDEX = os.path.join(P.AUDIT, "HASH-INDEX.csv")
MIGRATION = os.path.join(P.AUDIT, "MIGRATION-HASHES.csv")


def indexed_paths():
    r"""Every path either record already carries a hash for, lower-cased.

    Both files are read, because `master_sheet.load_hash_index` reads both and
    a tool that consulted only one would re-hash 64,683 files to learn nothing.
    """
    known = set()
    for src in (MIGRATION, HASH_INDEX):
        if not os.path.exists(src):
            continue
        with io.open(src, encoding="utf-8", errors="replace", newline="") as fh:
            for r in csv.reader(fh):
                if len(r) >= 3 and r[2] and len(r[2]) == 64:
                    known.add(r[0].lower())
    return known


def unhashed():
    known = indexed_paths()
    out = []
    with io.open(INVENTORY, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            p = r.get("LibraryPath") or ""
            if p and p.lower() not in known:
                out.append(p)
    return out, len(known)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=6,
                    help="hashing is disk-bound; more threads past a handful "
                         "buy nothing and make a spinning disk thrash")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    todo, known = unhashed()
    print("paths already hashed : {:,}".format(known))
    print("paths with NO hash   : {:,}".format(len(todo)))
    if not todo:
        print("nothing to do")
        return 0

    if a.limit:
        todo = todo[:a.limit]
        print("  limited to {:,}".format(len(todo)))

    total = 0
    for p in todo:
        try:
            total += os.path.getsize("\\\\?\\" + p)
        except OSError:
            pass
    print("  {:.1f} GB to read".format(total / 1024 ** 3))

    if not a.apply:
        print()
        print("REPORT ONLY - nothing written. Re-run with --apply.")
        for p in todo[:5]:
            print("   {}".format(p))
        return 0

    fresh = not os.path.exists(HASH_INDEX)
    done = failed = 0
    t0 = time.time()

    def one(p):
        try:
            return p, os.path.getsize("\\\\?\\" + p), content_hash(p)
        except OSError as e:
            return p, None, str(e)

    with io.open(HASH_INDEX, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if fresh:
            w.writerow(["LibraryPath", "Bytes", "Blake2b256"])
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for p, size, h in ex.map(one, todo):
                if size is None:
                    failed += 1
                    print("  FAILED {}: {}".format(p, h))
                    continue
                w.writerow([p, size, h])
                done += 1
                if done % 500 == 0:
                    fh.flush()
                    os.fsync(fh.fileno())
                    el = time.time() - t0
                    print("  {:,}/{:,}  ({:.0f}s)".format(done, len(todo), el),
                          flush=True)
        fh.flush()
        os.fsync(fh.fileno())

    print()
    print("hashed {:,} files in {:.0f}s, {:,} failed".format(
        done, time.time() - t0, failed))
    print("appended to {}".format(HASH_INDEX))
    print()
    print("Now, IN THIS ORDER:")
    print("  1. python stages/08_index/build_db.py      # the hashes reach the index")
    print("  2. python stages/05_enrich/backfill_thumbs.py")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
