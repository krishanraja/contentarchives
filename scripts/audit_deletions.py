"""For every deleted 'non-personal video', does the library still hold that content?
Matches by filename+size against the library. Anything with no match is a real loss."""
import csv, os
from collections import defaultdict

BS = chr(92)
LIB = "D:/PhotoLibrary"

# library: (lowername, size) and name -> sizes
lib_ns, lib_names = set(), defaultdict(set)
for dp, _, fns in os.walk(LIB):
    for fn in fns:
        try:
            s = os.path.getsize(os.path.join(dp, fn))
        except OSError:
            continue
        lib_ns.add((fn.lower(), s))
        lib_names[fn.lower()].add(s)

rows = []
with open("D:/_PhotoAudit/to-delete.csv", newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try:
            b = int(r["Bytes"])
        except (ValueError, KeyError):
            continue
        if r.get("Reason") != "non-personal video":
            continue
        rows.append((r["Path"], b))

safe, lost = [], []
for p, b in rows:
    name = os.path.basename(p).lower()
    if (name, b) in lib_ns:
        safe.append((p, b, "exact name+size in library"))
    elif name in lib_names:
        safe.append((p, b, "same name in library, different size"))
    else:
        lost.append((p, b))

print(f"non-personal video deletions examined : {len(rows):,}")
print(f"  content still present in library    : {len(safe):,}  "
      f"({sum(x[1] for x in safe)/1024**3:.2f} GB - these were extra copies)")
print(f"  NOT present anywhere - REAL LOSS    : {len(lost):,}  "
      f"({sum(x[1] for x in lost)/1024**3:.2f} GB)")

print()
print("REAL LOSSES, largest first")
print("-" * 76)
for p, b in sorted(lost, key=lambda x: -x[1])[:40]:
    print(f"  {b/1024**3:>6.2f} GB  {p}")
if len(lost) > 40:
    print(f"  ... and {len(lost)-40:,} more")

with open("D:/_PhotoAudit/deleted-not-recoverable.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Path", "Bytes"])
    w.writerows(sorted(lost, key=lambda x: -x[1]))
print()
print("written: D:/_PhotoAudit/deleted-not-recoverable.csv")
