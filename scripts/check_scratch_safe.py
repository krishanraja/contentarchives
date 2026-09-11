r"""Is my own scratch really scratch? Prove it before deleting it.

_machine-b_stage and _h_speedtest were created by this project, so deleting them
looks free. It is only free if everything inside them also exists in the
library. A staging folder is exactly where a file goes to be forgotten: the
copy landed, the ingest died, the bytes sit there and nothing else has them.

So hash every file in them and look for its hash in the library. Anything not
found is reported and NOTHING is deleted - the disk is the source of truth, and
a file missing from the library gets ingested, not removed.
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

SCRATCH = [r"D:\_h_speedtest", r"D:\_machine-b_stage",
           r"D:\_PhotoAudit\_pilot", r"D:\_PhotoAudit\_pilotfast",
           r"D:\_PhotoAudit\_pilotlow"]
IDX = r"D:\_PhotoAudit\lib-size-index.csv"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def fhash(p: str) -> str | None:
    try:
        d = hashlib.blake2b(digest_size=32)
        with open(lp(p), "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                d.update(b)
        return d.hexdigest()
    except OSError:
        return None


# sizes present in the library - a size that is absent means the bytes are absent
sizes: set[int] = set()
with open(IDX, encoding="utf-8") as f:
    rd = csv.reader(f)
    next(rd, None)
    for row in rd:
        sizes.add(int(row[0]))
print(f"library distinct sizes: {len(sizes):,}")

# for sizes that DO collide we must hash the library files of that size
lib_by_size: dict[int, list[str]] = {}
for root in P.INVENTORY_ROOTS:
    for dp, dns, fns in os.walk(root):
        if "_Catalog" in dp:
            continue
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                lib_by_size.setdefault(os.path.getsize(p), []).append(p)
            except OSError:
                continue

total = orphans = matched = 0
orphan_list: list[tuple[str, int]] = []
for s in SCRATCH:
    if not os.path.isdir(s):
        print(f"\n{s}: absent")
        continue
    n = o = 0
    nb = ob = 0
    for dp, dns, fns in os.walk(s):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            n += 1
            nb += sz
            if sz not in sizes:
                o += 1
                ob += sz
                orphan_list.append((p, sz))
                continue
            h = fhash(p)
            if h is None:
                o += 1
                ob += sz
                orphan_list.append((p, sz))
                continue
            if any(fhash(c) == h for c in lib_by_size.get(sz, [])):
                matched += 1
            else:
                o += 1
                ob += sz
                orphan_list.append((p, sz))
    total += n
    orphans += o
    print(f"\n{s}")
    print(f"  files {n:,} ({nb/1024**3:.2f} GB)   "
          f"NOT in library: {o:,} ({ob/1024**3:.2f} GB)")

print(f"\ntotal scratch files {total:,}   safe (in library) {matched:,}   "
      f"orphaned {orphans:,}")
if orphan_list:
    out = r"D:\_PhotoAudit\SCRATCH-ORPHANS.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Path", "Bytes"])
        w.writerows(orphan_list)
    print(f"VERDICT: DO NOT DELETE BLINDLY - {orphans:,} files exist nowhere "
          f"else. Listed in {out}; ingest them first.")
else:
    print("VERDICT: every scratch file exists in the library. Safe to delete.")
