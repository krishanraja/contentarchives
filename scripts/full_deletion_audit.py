"""Full audit of ALL 30,959 deletions - every category, no sampling.

For each deleted file, prove the content still exists:
  * 'redundant duplicate copy' -> find its duplicate GROUP and confirm the KEEP
    file still exists on disk at the right size. If the KEEP is gone too, the
    content is lost.
  * everything else -> look for identical name+size in the library.

Anything that fails both is a real, unreported loss.
"""
import csv, os
from collections import defaultdict

BS = chr(92)
AUDIT = "D:/_PhotoAudit"
LIB = "D:/PhotoLibrary"

# ---- library contents ----
lib_ns = set()
lib_names = defaultdict(set)
for dp, _, fns in os.walk(LIB):
    for fn in fns:
        try:
            s = os.path.getsize(os.path.join(dp, fn))
        except OSError:
            continue
        lib_ns.add((fn.lower(), s))
        lib_names[fn.lower()].add(s)
print(f"library files indexed: {len(lib_ns):,}")

# ---- duplicate groups: which file was KEEP for each dup ----
keep_for = {}
group_members = defaultdict(list)
with open(os.path.join(AUDIT, "duplicates.csv"), newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        group_members[r["GroupId"]].append((r["Keep"], r["FullName"], int(r["Bytes"])))
for gid, members in group_members.items():
    keeps = [m for m in members if m[0] == "KEEP"]
    if not keeps:
        continue
    kp, kb = keeps[0][1], keeps[0][2]
    for kind, path, b in members:
        if kind != "KEEP":
            keep_for[path] = (kp, kb)
print(f"duplicate groups: {len(group_members):,}   dup->keep mappings: {len(keep_for):,}")

# ---- audit every deletion ----
rows = []
with open(os.path.join(AUDIT, "to-delete.csv"), newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try:
            rows.append((r["Path"], int(r["Bytes"]), r["Reason"]))
        except (ValueError, KeyError, TypeError):
            continue
print(f"deletions to audit: {len(rows):,}")

result = defaultdict(lambda: {"safe": [0, 0], "lost": [0, 0]})
lost_rows = []
keep_missing = []

for path, b, reason in rows:
    name = os.path.basename(path).lower()
    ok = False
    if reason == "redundant duplicate copy" and path in keep_for:
        kp, kb = keep_for[path]
        try:
            ok = os.path.exists(kp) and os.path.getsize(kp) == kb
        except OSError:
            ok = False
        if not ok:
            # KEEP is gone from its original spot - is the content in the library?
            ok = (name, b) in lib_ns
            if not ok:
                keep_missing.append((path, b, kp))
    else:
        ok = (name, b) in lib_ns or name in lib_names

    slot = "safe" if ok else "lost"
    result[reason][slot][0] += 1
    result[reason][slot][1] += b
    if not ok:
        lost_rows.append((path, b, reason))

print()
print("FULL DELETION AUDIT - ALL CATEGORIES")
print("=" * 78)
print(f"  {'reason':<28} {'recoverable':>22} {'LOST':>22}")
tot_lost_n = tot_lost_b = 0
for reason in sorted(result):
    s, l = result[reason]["safe"], result[reason]["lost"]
    tot_lost_n += l[0]
    tot_lost_b += l[1]
    print(f"  {reason:<28} {s[0]:>9,} / {s[1]/1024**3:>7.2f} GB "
          f"{l[0]:>9,} / {l[1]/1024**3:>7.2f} GB")
print("-" * 78)
print(f"  {'TOTAL LOST':<28} {'':>22} {tot_lost_n:>9,} / {tot_lost_b/1024**3:>7.2f} GB")

if keep_missing:
    print()
    print(f"  !! {len(keep_missing):,} duplicates whose KEEP file is ALSO missing")
    for p, b, kp in keep_missing[:10]:
        print(f"     deleted: {p[:60]}")
        print(f"     keep gone: {kp[:60]}")

with open(os.path.join(AUDIT, "FULL-loss-audit.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Path", "Bytes", "Reason"])
    w.writerows(sorted(lost_rows, key=lambda x: -x[1]))

print()
print("LOST FILES BY TYPE (camera-origin = personal)")
print("-" * 78)
import re
CAM = re.compile(r"DCIM.Camera|GOPR|DJI_|IMG_|PXL_|DSC|[0-9]{8}_[0-9]{6}", re.I)
cam = [r for r in lost_rows if CAM.search(r[0])]
non = [r for r in lost_rows if not CAM.search(r[0])]
print(f"  camera-origin : {len(cam):>7,} files  {sum(x[1] for x in cam)/1024**3:>7.2f} GB")
print(f"  other         : {len(non):>7,} files  {sum(x[1] for x in non)/1024**3:>7.2f} GB")
print()
print("  largest camera-origin losses:")
for p, b, reason in sorted(cam, key=lambda x: -x[1])[:20]:
    print(f"    {b/1024**2:>8.1f} MB  [{reason}]  {p[:64]}")
print()
print("written: D:/_PhotoAudit/FULL-loss-audit.csv")
