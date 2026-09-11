"""Verify the head+tail duplicate signature against real full-content hashes,
on a random sample. If any group disagrees, the signature is unsafe."""
import csv, hashlib, random, os
from collections import defaultdict

DUP = r"D:\_PhotoAudit\duplicates.csv"
random.seed(7)

groups = defaultdict(list)
with open(DUP, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        groups[r["GroupId"]].append((r["FullName"], int(r["Bytes"])))

ids = list(groups)
print(f"total duplicate groups: {len(ids):,}")

# Sample across the size range: biggest 15, smallest 15, 40 random.
by_size = sorted(ids, key=lambda g: -groups[g][0][1])
sample = list(dict.fromkeys(by_size[:15] + by_size[-15:] + random.sample(ids, min(40, len(ids)))))
print(f"verifying {len(sample)} groups by full content hash ...\n")

def full(p):
    h = hashlib.blake2b(digest_size=16)
    with open(p, "rb", buffering=0) as f:
        while True:
            b = f.read(4 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

ok = bad = err = 0
bytes_read = 0
for g in sample:
    paths = groups[g]
    try:
        hs = set()
        for p, s in paths:
            hs.add(full(p))
            bytes_read += s
        if len(hs) == 1:
            ok += 1
        else:
            bad += 1
            print(f"  MISMATCH group {g} ({paths[0][1]/1024**2:.1f} MB):")
            for p, s in paths:
                print(f"     {p}")
    except OSError as e:
        err += 1

print(f"\n  groups verified identical : {ok}")
print(f"  groups that MISMATCHED    : {bad}")
print(f"  unreadable                : {err}")
print(f"  data hashed for the check : {bytes_read/1024**3:.2f} GB")
print("\n  VERDICT:", "signature is SAFE" if bad == 0 else "signature is UNSAFE - do not act on duplicates.csv")

print("\n=== sample of what would be dropped (largest groups) ===")
for g in by_size[:6]:
    paths = groups[g]
    print(f"\n  {paths[0][1]/1024**2:.0f} MB x {len(paths)} copies")
    for i, (p, s) in enumerate(paths):
        print(f"     {'KEEP' if i == 0 else 'dup '}  {p[:96]}")
