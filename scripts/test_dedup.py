"""Prove the archive dedup logic is content-proven, not name-based.
Uses a throwaway library in a temp dir. Touches nothing real."""
import os, sys, tarfile, tempfile, shutil, importlib

root = tempfile.mkdtemp(prefix="dedup_test_")
LIB  = os.path.join(root, "lib", "Library")
ND   = os.path.join(root, "lib", "NoDate")
CAT  = os.path.join(root, "lib", "_Catalog")
TMP  = os.path.join(root, "tmp")
for d in (LIB, ND, CAT, TMP):
    os.makedirs(d, exist_ok=True)

import autopilot as ap
ap.LIB, ap.NODATE, ap.CAT, ap.TMPDIR = LIB, ND, CAT, TMP
ap.ADDED  = os.path.join(root, "added.csv")
ap.DUPLOG = os.path.join(root, "dups.csv")
ap.LOGF   = os.path.join(root, "log.txt")
ap.MIN_D_GB, ap.MIN_C_GB = 0.0, 0.0
ap.AUDIT = root

# --- build a tiny "library" -------------------------------------------------
same     = b"AAAA" * 4096          # will also be in the archive, identical
collide  = b"BBBB" * 4096          # same NAME and same SIZE as an archive member,
                                   # but different bytes -> must NOT be treated as dup
os.makedirs(os.path.join(LIB, "2019", "2019-05"), exist_ok=True)
p_same    = os.path.join(LIB, "2019", "2019-05", "IMG_20190501_120000.jpg")
p_collide = os.path.join(LIB, "2019", "2019-05", "IMG_20190502_120000.jpg")
open(p_same, "wb").write(same)
open(p_collide, "wb").write(collide)

# --- build the test archive -------------------------------------------------
arc_dir = os.path.join(root, "arc"); os.makedirs(arc_dir, exist_ok=True)
members = {
    "Takeout/Google Photos/IMG_20190501_120000.jpg": same,                  # exact dup
    "Takeout/Google Photos/IMG_20190502_120000.jpg": b"CCCC" * 4096,        # NAME+SIZE clash, different bytes
    "Takeout/Google Photos/IMG_20190603_120000.jpg": b"DDDD" * 2048,        # brand new
}
for rel, data in members.items():
    fp = os.path.join(arc_dir, os.path.basename(rel))
    open(fp, "wb").write(data)
arc = os.path.join(root, "takeout-test-001.tgz")
with tarfile.open(arc, "w:gz") as t:
    for rel in members:
        t.add(os.path.join(arc_dir, os.path.basename(rel)), arcname=rel)

by_size, ns = ap.build_index()
print(f"library seeded: {sum(len(v) for v in by_size.values())} files")
n, d, sk, errs, total, res, complete = ap.ingest_archive(arc, by_size, ns, __import__("time").time())
print(f"result: new={n} dup={d} skipped={sk} errors={errs} resumed={res} media_total={total} complete={complete}")

placed = []
for dp, _, fns in os.walk(LIB):
    for fn in fns:
        placed.append(os.path.relpath(os.path.join(dp, fn), LIB))
for dp, _, fns in os.walk(ND):
    for fn in fns:
        placed.append("NoDate/" + fn)

print("\nlibrary now contains:")
for x in sorted(placed):
    print("   ", x)

fails = []
if d != 1:                    fails.append(f"expected exactly 1 content-verified duplicate, got {d}")
if n != 2:                    fails.append(f"expected 2 new files, got {n}")
if n + d + res != total:      fails.append("accounting mismatch")
if errs:                      fails.append(f"{errs} errors")
# the name+size clash must have survived under a suffixed name
clash = [x for x in placed if "IMG_20190502_120000" in x]
if len(clash) != 2:           fails.append(f"NAME+SIZE clash lost! expected 2 copies, found {len(clash)}: {clash}")
if open(p_collide,"rb").read() != collide: fails.append("original library file was overwritten")

print("\n" + ("PASS - dedup is content-proven; the name+size clash was preserved"
              if not fails else "FAIL:\n  " + "\n  ".join(fails)))
shutil.rmtree(root, ignore_errors=True)
sys.exit(1 if fails else 0)
