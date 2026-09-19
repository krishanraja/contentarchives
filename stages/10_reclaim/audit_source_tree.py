r"""Which media in a tree is ALREADY in the library, proven by content?

    python audit_source_tree.py --root E:\ --max-seconds 500
    python audit_source_tree.py --root E:\ --max-seconds 500   # resumes
    python audit_source_tree.py --root E:\ --report            # verdicts so far

Read-only. Deletes nothing, moves nothing, proposes nothing. It answers one
question per file - "does the library already hold these exact bytes?" - and
writes the answer down.

WHY NOT already_in_library.py

That tool answers the same question for a FIXED input list on D:, and it
computes its own 16-byte digest, which cannot be compared against `library.db`
at all - it re-walks and re-hashes the library every run to have something of
its own shape to compare with. Here the reference set is the index: 82,104
files, every one carrying the canonical blake2b-256 that every tag in the store
hangs off.

`content_hash` is IMPORTED, never reimplemented. A second implementation is how
two hashes of the same file end up incomparable, and that has already happened
once in this stage.

THE SIZE GATE IS THE WHOLE TRICK

The library has 77,882 distinct sizes across 82,104 files. A file whose size
appears nowhere in that set cannot be a duplicate of anything in it, so it is
settled as UNIQUE without a single byte being read. Only a size collision is
worth hashing. That is learning 7 used in the direction that saves work: size
rules out, only a hash rules in.

The converse is the trap this file must not fall into: equal size is NOT equal
content (learnings 22 and 36), so a size match is never a verdict - it is only
a reason to hash.

BOUNDED, RESUMABLE SLICES

E: is 102,657 media files and 1,068 GB. Hashing that is hours, and this machine
kills long jobs under memory pressure - three background jobs died tonight
inside minutes. So:

  every verdict is appended and fsynced the moment it is reached, never held in
  memory until the end (hash_283.py held its results, was killed an hour in, and
  lost all of it);

  --max-seconds stops cleanly at a boundary, so a run always fits inside a
  foreground call and a kill costs at most the file in flight;

  a re-run skips every path already recorded.

AN UNREADABLE FILE IS NOT A UNIQUE FILE

If a file cannot be hashed it is recorded as UNREADABLE, never as "no match".
Treating a failed hash as a non-match is exactly how 222 GB of byte-identical
duplicates were once admitted: `full_hash` returned None, `None == th` was
False, and every unreadable candidate silently became new.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
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
from store import content_hash  # noqa: E402  - imported, never reimplemented

DB = os.path.join(P.AUDIT, "library.db")

PHOTO = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.bmp', '.tif',
         '.tiff', '.webp', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf',
         '.orf', '.rw2', '.pef', '.srw'}
VIDEO = {'.mp4', '.mov', '.avi', '.m2ts', '.3gp', '.mkv', '.wmv', '.m4v',
         '.mpg', '.mpeg', '.webm', '.mts'}
MEDIA = PHOTO | VIDEO

SKIP_DIRS = {"$recycle.bin", "system volume information", "__pycache__",
             ".git", "_thumbs", "found.000"}

FIELDS = ["Path", "Bytes", "Verdict", "Hash", "HeldAt"]

csv.field_size_limit(1 << 30)


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def out_path(root: str) -> str:
    tag = "".join(c if c.isalnum() else "-" for c in root).strip("-").lower()
    return os.path.join(P.AUDIT, "SOURCE-AUDIT-{}.csv".format(tag))


def load_library():
    """(sizes, hash -> library path). The index, not a fresh walk of the disk."""
    con = sqlite3.connect("file:{}?mode=ro".format(DB.replace("\\", "/")),
                          uri=True)
    try:
        sizes = set()
        by_hash = {}
        for path, h, b in con.execute(
                "select path, hash, bytes from files where hash is not null"):
            if b is not None:
                sizes.add(int(b))
            if h:
                by_hash.setdefault(h.lower(), path)
        return sizes, by_hash
    finally:
        con.close()


def already_done(out: str) -> set:
    done = set()
    if not os.path.exists(out):
        return done
    with io.open(out, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            p = (r.get("Path") or "").strip()
            if p:
                done.add(p.lower())
    return done


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help=r"tree to audit, e.g. E:\ ")
    ap.add_argument("--max-seconds", type=float, default=500.0,
                    help="stop cleanly after this long so the run fits in one "
                         "foreground call; re-run to resume")
    ap.add_argument("--report", action="store_true",
                    help="summarise the verdicts recorded so far and stop")
    a = ap.parse_args()

    out = out_path(a.root)

    if a.report:
        if not os.path.exists(out):
            print("nothing audited yet for {}".format(a.root))
            return 1
        by = collections.Counter()
        gb = collections.Counter()
        with io.open(out, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                v = r["Verdict"]
                by[v] += 1
                try:
                    gb[v] += int(r["Bytes"] or 0)
                except ValueError:
                    pass
        print("{}  ({})".format(a.root, os.path.basename(out)))
        print()
        for v, n in by.most_common():
            print("  {:<12} {:>8,} files  {:>9.1f} GB".format(
                v, n, gb[v] / (1 << 30)))
        print()
        print("  {:<12} {:>8,} files  {:>9.1f} GB".format(
            "TOTAL", sum(by.values()), sum(gb.values()) / (1 << 30)))
        held = gb.get("HELD", 0) / (1 << 30)
        if held:
            print()
            print("  {:.1f} GB is byte-identical to content the library already".format(held))
            print("  holds. That is what COULD be freed - not a recommendation,")
            print("  and not until the second copy is proven for those files.")
        return 0

    if not os.path.isdir(a.root):
        print("no such root: {}".format(a.root))
        return 1

    print("loading the library index...")
    sizes, by_hash = load_library()
    print("  {:,} distinct sizes, {:,} hashes".format(len(sizes), len(by_hash)))

    done = already_done(out)
    if done:
        print("  resuming: {:,} file(s) already audited".format(len(done)))

    fresh = not os.path.exists(out)
    t0 = time.time()
    n_new = held = unique = unreadable = skipped_size = 0
    bytes_hashed = 0

    fh = io.open(out, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if fresh:
        w.writerow(FIELDS)
        fh.flush()
        os.fsync(fh.fileno())

    try:
        for dp, dns, fns in os.walk(a.root):
            dns[:] = [d for d in dns if d.lower() not in SKIP_DIRS]
            if time.time() - t0 > a.max_seconds:
                break
            for fn in fns:
                if time.time() - t0 > a.max_seconds:
                    break
                if os.path.splitext(fn)[1].lower() not in MEDIA:
                    continue
                p = os.path.join(dp, fn)
                if p.lower() in done:
                    continue
                try:
                    size = os.path.getsize(lp(p))
                except OSError:
                    w.writerow([p, "", "UNREADABLE", "", ""])
                    unreadable += 1
                    n_new += 1
                    continue

                if size not in sizes:
                    # No size match anywhere in 82,104 files: it cannot be a
                    # duplicate of any of them. Settled without reading a byte.
                    w.writerow([p, size, "UNIQUE", "", ""])
                    unique += 1
                    skipped_size += 1
                else:
                    try:
                        h = content_hash(p)
                    except OSError as e:
                        # NOT a non-match. A file that will not hash is
                        # unproven, and calling it unique is how 222 GB of
                        # duplicates were once admitted.
                        w.writerow([p, size, "UNREADABLE", "", str(e)[:120]])
                        unreadable += 1
                        n_new += 1
                        continue
                    bytes_hashed += size
                    lib = by_hash.get(h.lower())
                    if lib:
                        w.writerow([p, size, "HELD", h, lib])
                        held += 1
                    else:
                        w.writerow([p, size, "UNIQUE", h, ""])
                        unique += 1
                n_new += 1

                # Durable, but not once per file.
                #
                # An fsync per verdict cost more than the work it protected:
                # the first slice managed 3,509 files in 482s, and most of those
                # files were never even read - they were settled by the size
                # gate, so the only I/O was the fsync itself. Against 102,657
                # files that is hours spent protecting milliseconds.
                #
                # The rule that matters is unchanged: nothing is held only in
                # memory. Verdicts are flushed every 50 files and at every exit
                # path, so a kill costs at most 50 rows of a re-runnable scan -
                # against hash_283.py, which held an hour of work in memory and
                # lost all of it. Cheap to redo, and bounded.
                if n_new % 50 == 0:
                    fh.flush()
                    os.fsync(fh.fileno())

                if n_new % 200 == 0:
                    el = time.time() - t0
                    print("  {:,} new  held {:,}  unique {:,}  "
                          "({:.1f} GB hashed, {:.0f}s)".format(
                              n_new, held, unique,
                              bytes_hashed / (1 << 30), el), flush=True)
    finally:
        # Every exit path lands the verdicts, including the timed stop and a
        # KeyboardInterrupt. A buffered write that is never flushed is the same
        # as work never done.
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            pass
        fh.close()

    el = time.time() - t0
    print()
    print("this slice: {:,} file(s) in {:.0f}s".format(n_new, el))
    print("  HELD        : {:,}".format(held))
    print("  UNIQUE      : {:,}  ({:,} ruled out by size alone, never read)".format(
        unique, skipped_size))
    print("  UNREADABLE  : {:,}".format(unreadable))
    print("  hashed      : {:.1f} GB".format(bytes_hashed / (1 << 30)))
    print()
    print("re-run the same command to continue; --report for the running total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
