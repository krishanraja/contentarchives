r"""Which freeable files on D: have their content already safely in the library?

The space audit split files by whether they share an inode with a library entry.
That catches hardlinks, but misses a whole category: a file that was ingested as a
*copy* from a cloud source, and whose identical twin still sits on D: as a separate
inode. Dedupe correctly refused to add it twice, so the D: copy was left alone - and
its bytes are redundant, not precious.

The funeral video is the worked example. It lives in the library, copied from a
Drive mount, and two more copies sit in laptop backup folders on D:. Deleting those
two frees real space and loses nothing.

This proves that relationship per file, by whole-file hash, against the library.
Only an exact content match counts. Never a filename, never a size.

Read-only. Produces a verified list; deletes nothing.
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SRC = r"D:\_PhotoAudit\SPACE-FREEABLE.csv"
OUT = r"D:\_PhotoAudit\SAFE-ALREADY-IN-LIBRARY.csv"
LIB_ROOTS = [r"D:\ContentLibrary", r"D:\ContentLibrary\ContentProduction", r"D:\ContentLibrary\Archive"]
MIN_SIZE = 64 * 1024          # below this the bookkeeping outweighs the bytes


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def file_hash(path: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    with open(lp(path), "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    # --- index the library by size first: no size match, no possible duplicate
    lib_by_size: dict[int, list[str]] = defaultdict(list)
    n = 0
    for root in LIB_ROOTS:
        for dp, _, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    lib_by_size[os.path.getsize(lp(p))].append(p)
                    n += 1
                except OSError:
                    pass
    print(f"library: {n:,} files, {len(lib_by_size):,} distinct sizes")

    rows = []
    with open(SRC, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            size = int(r["Bytes"])
            if size >= MIN_SIZE and size in lib_by_size:
                rows.append((size, r["Path"]))
    rows.sort(reverse=True)
    print(f"candidates (size matches a library file): {len(rows):,}, "
          f"{sum(s for s, _ in rows)/1024**3:.1f} GB")
    print("hashing to prove content identity...")

    lib_hash_cache: dict[str, str] = {}
    proven = []
    checked = 0
    for size, path in rows:
        checked += 1
        if checked % 500 == 0:
            print(f"  {checked:,}/{len(rows):,}  proven so far: {len(proven):,} "
                  f"({sum(s for s, _, _ in proven)/1024**3:.1f} GB)", flush=True)
        try:
            h = file_hash(path)
        except OSError:
            continue
        match = None
        for cand in lib_by_size[size]:
            ch = lib_hash_cache.get(cand)
            if ch is None:
                try:
                    ch = lib_hash_cache[cand] = file_hash(cand)
                except OSError:
                    continue
            if ch == h:
                match = cand
                break
        if match:
            proven.append((size, path, match))

    total = sum(s for s, _, _ in proven)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Bytes", "RedundantPath", "LibraryCopy", "Proof"])
        for size, path, match in proven:
            w.writerow([size, path, match, "whole-file blake2b match"])

    print()
    print("=" * 88)
    print(f"  {len(proven):,} files on D: are byte-identical to a file already in "
          f"the library")
    print(f"  {total/1024**3:.1f} GB can be freed with the content provably retained")
    print("=" * 88)
    print()
    for size, path, match in proven[:30]:
        print(f"  {size/1024**2:>8.1f} MB  {path[:70]}")
        print(f"  {'':>8}     kept: {match[:70]}")

    folders = defaultdict(lambda: [0, 0])
    for size, path, _ in proven:
        d = os.path.dirname(path)
        folders[d][0] += 1
        folders[d][1] += size
    print()
    print("BY FOLDER")
    print("=" * 88)
    for d, (cnt, b) in sorted(folders.items(), key=lambda kv: -kv[1][1])[:25]:
        print(f"  {cnt:>6,} {b/1024**3:>8.2f} GB  {d[:66]}")

    print()
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
