r"""Will 371 GB of H: fit in 272 GB of D:? Bound it before spending eight hours.

H: has no hashes - hashing off the mount hangs (learning 15) - so an exact
answer is not available without copying, which is the thing being sized. But
size alone bounds it usefully:

  a file whose SIZE appears nowhere in the library is certainly new
  a file whose size does appear MIGHT be a duplicate, and might not

So: new_bytes_floor counts only the certainly-new files. That is the smallest
D: can possibly grow, and if even that exceeds free space, the run cannot
complete in one pass and there is no point starting it as one.

Also folds in the routing signature, because the answer differs by destination:
work artifacts and documents leaving the chronology still occupy disk.
"""

from __future__ import annotations

import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                              # noqa: E402
from survey_h_folders import CAMERA, WORK, NEVER, H_ROOT       # noqa: E402

LIB_INDEX = r"D:\_PhotoAudit\lib-size-index.csv"
SKIP_FOLDERS = {"_audit-trail", "in", "out"}     # this project's own tooling

# ---- library sizes -------------------------------------------------------
# Built by lib_size_index.py from the whole library. Coverage is asserted
# against the disk below, because the previous index silently covered 29%.
lib_sizes: collections.Counter = collections.Counter()
n = 0
with open(LIB_INDEX, encoding="utf-8", errors="replace") as f:
    rd = csv.reader(f)
    next(rd, None)
    for row in rd:
        if len(row) < 2:
            continue
        lib_sizes[int(row[0])] += int(row[1])
        n += int(row[1])

on_disk = 0
for root in P.INVENTORY_ROOTS:
    for dp, dns, fns in os.walk(root):
        if "_Catalog" not in dp:
            on_disk += len(fns)
print(f"library size index: {n:,} files, {len(lib_sizes):,} distinct sizes")
print(f"library on disk   : {on_disk:,} files   coverage "
      f"{n*100/max(on_disk,1):.1f}%")
if n < on_disk * 0.99:
    sys.exit("REFUSING: the index does not cover the library. Re-run "
             "lib_size_index.py - a partial index calls old files new.")

# ---- walk H: -------------------------------------------------------------
tot_files = tot_bytes = 0
certain_new_files = certain_new_bytes = 0
maybe_dup_files = maybe_dup_bytes = 0
per_folder: dict[str, list[int]] = {}
route: collections.Counter = collections.Counter()
route_bytes: collections.Counter = collections.Counter()

for folder in sorted(os.listdir(H_ROOT)):
    root = os.path.join(H_ROOT, folder)
    if not os.path.isdir(root) or folder in SKIP_FOLDERS:
        continue
    cf = cb = mf = mb = 0
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in NEVER:
                continue
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if sz == 0:
                continue
            tot_files += 1
            tot_bytes += sz
            rel = os.path.relpath(p, root)
            r = ("chronology" if CAMERA.search(rel)
                 else "production/archive" if WORK.search(rel)
                 else "undecided")
            route[r] += 1
            route_bytes[r] += sz
            if lib_sizes.get(sz):
                mf += 1
                mb += sz
            else:
                cf += 1
                cb += sz
    certain_new_files += cf
    certain_new_bytes += cb
    maybe_dup_files += mf
    maybe_dup_bytes += mb
    per_folder[folder] = [cf, cb, mf, mb]

gb = lambda b: b / 1024 ** 3                                        # noqa: E731
free = __import__("shutil").disk_usage("D:\\").free

print(f"\nH: to consider (excluding {', '.join(sorted(SKIP_FOLDERS))}):")
print(f"  {tot_files:,} files, {gb(tot_bytes):.1f} GB")
print(f"  certainly new (size unseen in library): {certain_new_files:,} files, "
      f"{gb(certain_new_bytes):.1f} GB   <-- D: MUST absorb at least this")
print(f"  possibly duplicate (size collides)    : {maybe_dup_files:,} files, "
      f"{gb(maybe_dup_bytes):.1f} GB")
print(f"\nD: free now: {gb(free):.1f} GB   floor to keep: 60.0 GB   "
      f"usable: {gb(free)-60:.1f} GB")
verdict = ("FITS in one pass" if gb(certain_new_bytes) < gb(free) - 60
           else "DOES NOT FIT - needs staging in two passes or reclaim first")
print(f"VERDICT: {verdict}")

print("\nby folder (certainly-new / maybe-dup):")
for f, (cf, cb, mf, mb) in sorted(per_folder.items(),
                                  key=lambda x: -x[1][1]):
    print(f"  {f[:44]:<46} new {cf:>6,} {gb(cb):>7.1f} GB   "
          f"dup? {mf:>6,} {gb(mb):>7.1f} GB")

print("\nrouting signature across all of it:")
for r, c in route.most_common():
    print(f"  {r:<20} {c:>7,} files  {gb(route_bytes[r]):>7.1f} GB")
