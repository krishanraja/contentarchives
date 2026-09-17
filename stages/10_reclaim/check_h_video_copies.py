r"""Are the 283 unproven videos on H: really held in the library, or unique?

Krish, 2026-09-19: "check the videos".

These are the files tonight's clear PROTECTED: on H: in
`_photo-consolidation`, not traceable into the library by provenance, name+size
or size. 283 `.mp4` files, 10.63 GB. Among them are names carrying `__v0` and
`__v2` suffixes, which is exactly what `video_variants.py` exists to reason
about - and its warning matters here:

    CHAPTERS   GoPro splits long recordings into GH01xxxx, GH02xxxx... These
               are NOT duplicates - they are consecutive parts of one
               recording, and deleting the "extra" ones loses the second half
               of the take.

So this does not decide anything by name. For each file it asks:

  1. Is there a library file with the SAME SIZE? (a hash-identical copy has
     the same size, so no size match means no identical copy)
  2. Is there a library file whose name is the same once the `__vN` suffix and
     any `(1)`-style suffix is stripped?
  3. What does the library hold that looks like the same recording - same base
     name, any size?

Reading the H: file itself would hydrate it from Drive, so nothing here opens
one. Metadata only; decides nothing; writes a report.
"""
import collections
import csv
import io
import os
import re
import sqlite3
import sys

REPO = r"C:\Users\krish\dev\contentarchives"
sys.path.insert(0, REPO)
import stagepath  # noqa: E402,F401
import paths as P                                                 # noqa: E402

csv.field_size_limit(10 * 1024 * 1024)
KEEP = os.path.join(P.AUDIT, "H-SOURCE-NOT-HELD.csv")
OUT = os.path.join(P.AUDIT, "H-VIDEOS-VERDICT.csv")

VARIANT = re.compile(r"__v\d+(?:-[0-9A-Fa-f-]+)?$")
PAREN = re.compile(r"\s*\(\d+\)$")


def base_of(name: str) -> str:
    stem, ext = os.path.splitext(name)
    stem = VARIANT.sub("", stem)
    stem = PAREN.sub("", stem)
    return (stem + ext).lower()


rows = [r for r in csv.DictReader(io.open(KEEP, encoding="utf-8", newline=""))]
vids = [r for r in rows
        if os.path.splitext(r["HPath"])[1].lower() in
        (".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".mpg", ".mpeg",
         ".wmv", ".mts", ".m2ts", ".webm")]
print("protected files: {:,}   of which video: {:,}  ({:.2f} GB)".format(
    len(rows), len(vids),
    sum(int(r["Bytes"] or 0) for r in vids) / (1 << 30)))

db = sqlite3.connect("file:{}?mode=ro".format(
    os.path.join(P.AUDIT, "library.db").replace("\\", "/")), uri=True)
by_size = collections.defaultdict(list)
by_base = collections.defaultdict(list)
for path, nbytes in db.execute("select path, bytes from files"):
    if nbytes is None:
        continue
    by_size[nbytes].append(path)
    by_base[base_of(os.path.basename(path or ""))].append((path, nbytes))
db.close()
print("library: {:,} distinct sizes, {:,} distinct base names".format(
    len(by_size), len(by_base)))

verdicts = collections.Counter()
out_rows = []
for r in vids:
    p = r["HPath"]
    size = int(r["Bytes"] or 0)
    name = os.path.basename(p)
    base = base_of(name)

    size_hit = by_size.get(size) or []
    base_hit = by_base.get(base) or []

    if size_hit:
        v = "SAME SIZE in the library - very likely the identical copy"
        note = size_hit[0]
    elif base_hit:
        sizes = ", ".join("{:,}".format(s) for _, s in base_hit[:3])
        v = "same recording by name, DIFFERENT size - a variant, not a copy"
        note = "library has {} at {} bytes".format(
            os.path.basename(base_hit[0][0]), sizes)
    else:
        v = "NOTHING like it in the library - treat as unique"
        note = ""
    verdicts[v] += 1
    out_rows.append((p, size, name, base, v, note))

print()
print("=== verdicts ===")
for v, n in verdicts.most_common():
    gb = sum(s for _, s, _, _, vv, _ in out_rows if vv == v) / (1 << 30)
    print("  {:>4}  {:>7.2f} GB  {}".format(n, gb, v))

print()
print("=== the ones with nothing like them, biggest first ===")
uniq = [t for t in out_rows if t[4].startswith("NOTHING")]
for p, size, name, base, v, note in sorted(uniq, key=lambda t: -t[1])[:20]:
    print("  {:>13,}  {}".format(size, name[:70]))
print("  ... {} in total, {:.2f} GB".format(
    len(uniq), sum(t[1] for t in uniq) / (1 << 30)))

print()
print("=== variant-suffixed names, and what the library has instead ===")
var = [t for t in out_rows if VARIANT.search(os.path.splitext(t[2])[0])]
for p, size, name, base, v, note in sorted(var, key=lambda t: -t[1])[:12]:
    print("  {:>13,}  {}".format(size, name[:64]))
    print("      -> {}".format(v))
    if note:
        print("         {}".format(note[:88]))
print("  ... {} variant-named file(s)".format(len(var)))

tmp = OUT + ".tmp"
with io.open(tmp, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["HPath", "Bytes", "Name", "BaseName", "Verdict", "Evidence"])
    for t in sorted(out_rows, key=lambda t: -t[1]):
        w.writerow(t)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, OUT)
print()
print("written: {}".format(OUT))
print()
print("NOTHING DELETED. A size match is strong evidence of an identical copy;")
print("a name match with a different size is a VARIANT and may be the only one.")
