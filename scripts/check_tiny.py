r"""Were any of the files skipped as "too small" actually photographs?

ingest_tree.py skips media under 20 KB on the assumption they are stickers, icons
or thumbnails. That assumption is fine as a default and dangerous as a final answer:
WhatsApp compresses aggressively, and a genuine photo - especially one forwarded
several times - can land well under 20 KB.

The snapshots are about to be deleted, so this is the last moment the question can
be asked. Checks each skipped file for JPEG image dimensions, read from the header
without decoding. A 1600x1200 JPEG is a photograph whatever it weighs; a 96x96 one
is an icon.
"""

from __future__ import annotations

import csv
import os
import struct
from collections import Counter

SRC = r"D:\_PhotoAudit\INGEST-whatsapp.csv"
OUT = r"D:\_PhotoAudit\TINY-REVIEW.csv"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def jpeg_size(path: str):
    """Width and height from the SOF marker, without decoding the image."""
    try:
        with open(lp(path), "rb") as f:
            if f.read(2) != b"\xff\xd8":
                return None
            while True:
                b = f.read(1)
                while b and b != b"\xff":
                    b = f.read(1)
                while b == b"\xff":
                    b = f.read(1)
                if not b:
                    return None
                marker = b[0]
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                    continue
                data = f.read(2)
                if len(data) < 2:
                    return None
                seglen = struct.unpack(">H", data)[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    rest = f.read(5)
                    if len(rest) < 5:
                        return None
                    h, w = struct.unpack(">HH", rest[1:5])
                    return w, h
                f.seek(seglen - 2, 1)
    except OSError:
        return None


rows = []
for r in csv.DictReader(open(SRC, encoding="utf-8", errors="ignore")):
    if r["Outcome"] == "skipped-tiny":
        rows.append(r["Source"])

print(f"{len(rows):,} files were skipped as too small")

verdicts = Counter()
out = []
for p in rows:
    dims = jpeg_size(p)
    try:
        size = os.path.getsize(lp(p))
    except OSError:
        size = 0
    ext = os.path.splitext(p)[1].lower()
    if dims is None:
        v = "not-a-jpeg"
    else:
        w, h = dims
        # An icon or sticker is small in pixels. A photo is not, however few
        # bytes it has been squeezed into.
        v = "PHOTO" if max(w, h) >= 640 else ("borderline" if max(w, h) >= 320
                                              else "icon-or-sticker")
    verdicts[v] += 1
    out.append([v, size, dims[0] if dims else "", dims[1] if dims else "", ext, p])

print()
for v, n in verdicts.most_common():
    print(f"  {n:>6,}  {v}")

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Verdict", "Bytes", "Width", "Height", "Ext", "Path"])
    w.writerows(sorted(out, key=lambda r: (r[0] != "PHOTO", -r[1])))

photos = [r for r in out if r[0] in ("PHOTO", "borderline")]
if photos:
    print()
    print("REAL IMAGES THAT WOULD HAVE BEEN LOST  (largest first)")
    print("-" * 76)
    for r in sorted(photos, key=lambda r: -r[1])[:25]:
        print(f"  {r[1]/1024:>7.1f} KB  {r[2]}x{r[3]:<6}  {os.path.basename(r[5])[:44]}")
    print()
    print(f"  {len(photos):,} files, {sum(r[1] for r in photos)/1024**2:.1f} MB")
    print("  These need ingesting before the snapshots are deleted.")
else:
    print()
    print("  None of the skipped files are photographs. Safe to let them go.")

print()
print(f"written: {OUT}")
