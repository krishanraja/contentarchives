r"""Prove the 278 size-matched videos are byte-identical, not merely equal-sized.

Learning 22 on this project: equal size is not equal content. Learning 36: name
plus size never declares a duplicate. A 2026-09-07 case had two files of the
same name and the same size holding different content, and the whole dedup
design exists because of it.

So before anything is deleted, every one of these is hashed on BOTH sides:

  the H: copy  - which means DOWNLOADING it from Drive, because it is a
                 placeholder. 10.63 GB total, which is affordable; the 495 GB
                 that made this impossible for the whole source tree is not.
  the library copy - already on D:, cheap to read.

A pair that does not match is reported and kept. This writes a verdict file and
deletes nothing.
"""
import collections
import csv
import hashlib
import io
import os
import sqlite3
import sys
import time

REPO = r"C:\Users\krish\dev\contentarchives"
sys.path.insert(0, REPO)
import stagepath  # noqa: E402,F401
import paths as P                                                 # noqa: E402

csv.field_size_limit(10 * 1024 * 1024)
SRC = os.path.join(P.AUDIT, "H-VIDEOS-VERDICT.csv")
OUT = os.path.join(P.AUDIT, "H-VIDEOS-HASHED.csv")
CHUNK = 8 << 20


def blake(path: str, long_ok: bool = True) -> str | None:
    """blake2b-256. No \\?\ prefix on the H: mount - it is not accepted there."""
    p = path
    if long_ok and not path.startswith("H:") and not path.startswith("\\\\?\\"):
        p = "\\\\?\\" + path
    try:
        d = hashlib.blake2b(digest_size=32)
        with open(p, "rb", buffering=0) as f:
            for b in iter(lambda: f.read(CHUNK), b""):
                d.update(b)
        return d.hexdigest()
    except OSError as e:
        print("    unreadable: {}".format(e))
        return None


rows = [r for r in csv.DictReader(io.open(SRC, encoding="utf-8", newline=""))
        if r["Verdict"].startswith("SAME SIZE")]
print("size-matched videos to verify: {}  ({:.2f} GB to download)".format(
    len(rows), sum(int(r["Bytes"] or 0) for r in rows) / (1 << 30)))

db = sqlite3.connect("file:{}?mode=ro".format(
    os.path.join(P.AUDIT, "library.db").replace("\\", "/")), uri=True)
by_size = collections.defaultdict(list)
libhash = {}
for path, nbytes, h in db.execute("select path, bytes, hash from files"):
    if nbytes is None:
        continue
    by_size[nbytes].append(path)
    if h:
        libhash[path] = h
db.close()

# APPEND PER FILE, AND RESUME. A kill costs one row, not the whole run.
#
# The first version accumulated every verdict in memory and wrote the CSV once
# at the end. It was killed for low memory after downloading several GB from
# Drive and lost ALL of it - while `mirror_to_h.py`, written an hour earlier,
# carries a comment explaining exactly why its journal is append-only and
# fsynced. I wrote the lesson down and then did not apply it to my own script.
done = {}
if os.path.exists(OUT):
    with io.open(OUT, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("HPath"):
                done[r["HPath"].lower()] = r
    print("resuming: {} already verified".format(len(done)))

todo = [r for r in rows if r["HPath"].lower() not in done]
print("to verify now: {}  ({:.2f} GB to download)".format(
    len(todo), sum(int(r["Bytes"] or 0) for r in todo) / (1 << 30)))

fresh = not os.path.exists(OUT)
identical = differ = unreadable = 0
t0 = time.time()
read_b = 0
with io.open(OUT, "a", encoding="utf-8", newline="") as jf:
    w = csv.writer(jf)
    if fresh:
        w.writerow(["HPath", "Bytes", "Blake2b", "LibraryMatch", "Verdict"])
        jf.flush()
        os.fsync(jf.fileno())
    for i, r in enumerate(todo, 1):
        hp = r["HPath"]
        size = int(r["Bytes"] or 0)
        cands = by_size.get(size) or []
        hh = blake(hp)
        if hh is None:
            unreadable += 1
            w.writerow([hp, size, "", "", "H: COPY UNREADABLE - kept"])
        else:
            match = None
            for c in cands:
                ch = libhash.get(c) or blake(c)
                if ch and ch == hh:
                    match = c
                    break
            if match:
                identical += 1
                w.writerow([hp, size, hh, match,
                            "IDENTICAL - safe to delete from H:"])
            else:
                differ += 1
                w.writerow([hp, size, hh, "",
                            "SAME SIZE but DIFFERENT CONTENT - keep, unique"])
        jf.flush()
        os.fsync(jf.fileno())
        read_b += size
        if i % 10 == 0:
            el = time.time() - t0
            print("  {}/{}  {:.2f} GB read  {:.1f} MB/s  identical={} "
                  "differ={} unreadable={}".format(
                      i, len(todo), read_b / (1 << 30),
                      read_b / (1 << 20) / max(el, 1),
                      identical, differ, unreadable), flush=True)

out = list(done.values())

print()
print("=== verified by content, not by size ===")
print("  identical to a library file : {}".format(identical))
print("  SAME SIZE, DIFFERENT bytes  : {}   <- these are unique, keep them".format(
    differ))
print("  H: copy unreadable          : {}".format(unreadable))
print()
print("written: {}".format(OUT))
for row in out:
    if row[4].startswith("SAME SIZE but"):
        print("  KEEP: {}".format(row[0]))
