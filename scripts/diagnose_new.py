r"""Why is the archive ingest calling almost everything new?

Dedup is on content hash, so a RE-ENCODED copy of a photo already held is not a
duplicate and will be added. Correct behaviour, possibly the wrong outcome: the
library would gain a second, visually identical copy of thousands of images,
which is the opposite of consolidating.

THE BASELINE MUST EXCLUDE THIS RUN. The library index grows as the run adds to
it, so comparing new members against the live index asks whether the file we
just added is present - it always is. The first version of this script did
exactly that and reported a meaningless 100%.

So the baseline here is the library MINUS everything this archive contributed,
and the comparison is on size, not merely on the name existing.
"""
from __future__ import annotations
import csv, json, os, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopilot as ap

ARCHIVE = "takeout-20260907T082613Z-1-001.zip"
CP = rf"D:\_PhotoAudit\arc-progress\{ARCHIVE}.csv"
ADDED = r"D:\_PhotoAudit\autopilot-added.csv"
SIZES = r"D:\_PhotoAudit\arc-sizes.json"

# member -> size, from the cache ingest_eta.py already built
cache = json.load(open(SIZES, encoding="utf-8"))
msizes = {}
for k, v in cache.items():
    if k.startswith(ARCHIVE + "|"):
        msizes = v
        break
print(f"archive members with known size: {len(msizes):,}")

# live index
_by_size, ns = ap.build_index()
by_name = defaultdict(set)
for name, size in ns:
    by_name[name].add(size)

# subtract what THIS archive added, to get the pre-run baseline
removed = 0
with open(ADDED, newline="", encoding="utf-8", errors="replace") as f:
    for row in csv.reader(f):
        if len(row) >= 2 and ARCHIVE in row[1]:
            b = os.path.basename(row[0]).lower()
            try:
                s = os.path.getsize(row[0])
            except OSError:
                continue
            if b in by_name and s in by_name[b]:
                by_name[b].discard(s)
                if not by_name[b]:
                    del by_name[b]
                removed += 1
print(f"baseline = library minus {removed:,} files this archive added")
print(f"baseline distinct basenames: {len(by_name):,}\n")

cat = Counter(); ex = defaultdict(list)
with open(CP, newline="", encoding="utf-8", errors="replace") as f:
    for row in csv.reader(f):
        if len(row) < 2 or row[1] != "new":
            continue
        member = row[0]
        base = os.path.basename(member).lower()
        msize = msizes.get(member)
        sizes = by_name.get(base)
        if not sizes:
            cat["basename not in library - genuinely new"] += 1
        elif msize is None:
            cat["member size unknown"] += 1
        elif msize in sizes:
            cat["same name AND size - hash differs (true variant)"] += 1
            if len(ex["h"]) < 6: ex["h"].append((base, msize, sorted(sizes)))
        else:
            cat["same name, DIFFERENT size - re-encode/variant"] += 1
            if len(ex["d"]) < 8: ex["d"].append((base, msize, sorted(sizes)))

total = sum(cat.values())
print(f"members marked 'new' so far: {total:,}\n")
for k, v in cat.most_common():
    print(f"  {v:7,}  {v*100.0/total:5.1f}%  {k}")
for key, label in (("d", "same name, different size"), ("h", "same name and size")):
    if ex[key]:
        print(f"\nexamples - {label}  (archive size vs library size(s)):")
        for b, ms, ls in ex[key]:
            print(f"  {b:<46} archive={ms:>10,}  library={ls}")

# --- direction of the size difference: which copy is better? ---
print("\n" + "="*70)
print("DIRECTION of the difference - which copy is the better one?")
print("="*70)
smaller = larger = 0
sm_arch_b = sm_lib_b = 0
lg_arch_b = lg_lib_b = 0
worst = []
with open(CP, newline="", encoding="utf-8", errors="replace") as f:
    for row in csv.reader(f):
        if len(row) < 2 or row[1] != "new":
            continue
        base = os.path.basename(row[0]).lower()
        msize = msizes.get(row[0]); sizes = by_name.get(base)
        if not sizes or msize is None or msize in sizes:
            continue
        best_lib = max(sizes)
        if msize < best_lib:
            smaller += 1; sm_arch_b += msize; sm_lib_b += best_lib
            worst.append((best_lib / max(msize,1), base, msize, best_lib))
        else:
            larger += 1; lg_arch_b += msize; lg_lib_b += best_lib

GB = 1024**3
print(f"\narchive copy SMALLER than library  : {smaller:,}  "
      f"(adds {sm_arch_b/GB:.2f} GB beside {sm_lib_b/GB:.2f} GB already held)")
print(f"archive copy LARGER than library   : {larger:,}  "
      f"(adds {lg_arch_b/GB:.2f} GB, library holds {lg_lib_b/GB:.2f} GB)")
worst.sort(reverse=True)
print("\nlargest quality gaps (library is this many times bigger):")
for ratio, b, ms, ls in worst[:10]:
    print(f"  {ratio:6.1f}x  {b:<40} archive={ms/1e6:8.1f} MB  library={ls/1e6:8.1f} MB")
