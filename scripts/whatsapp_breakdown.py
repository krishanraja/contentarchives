r"""What exactly would the WhatsApp ingest add to the library?

13,633 new files against 13 duplicates is a large change - roughly a quarter again
on top of the existing library - so it gets looked at before it is committed, not
after. WhatsApp media is a mix: real photographs people sent, and a long tail of
stickers, animated GIFs and forwarded junk that is not a memory in any sense.
"""

from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict

SRC = r"D:\_PhotoAudit\INGEST-whatsapp.csv"
BS = chr(92)

folders = Counter()
folder_bytes = defaultdict(int)
ext = Counter()
ext_bytes = defaultdict(int)
sizes = []
n = 0

for r in csv.DictReader(open(SRC, encoding="utf-8", errors="ignore")):
    if r["Outcome"] != "new":
        continue
    n += 1
    s = r["Source"]
    parts = s.split(BS)
    # the folder directly under Media\, e.g. "WhatsApp Images"
    key = "(other)"
    for i, p in enumerate(parts):
        if p.lower() == "media" and i + 1 < len(parts):
            key = parts[i + 1]
            break
    try:
        size = os.path.getsize(s)
    except OSError:
        size = 0
    folders[key] += 1
    folder_bytes[key] += size
    e = os.path.splitext(s)[1].lower()
    ext[e] += 1
    ext_bytes[e] += size
    sizes.append((size, s))

print(f"new files that would be added: {n:,}")
print()
print("BY WHATSAPP FOLDER")
print("-" * 68)
for k, v in folders.most_common(20):
    print(f"  {v:>7,}  {folder_bytes[k]/1024**2:>9.1f} MB  {k}")
print()
print("BY EXTENSION")
print("-" * 68)
for k, v in ext.most_common(12):
    print(f"  {v:>7,}  {ext_bytes[k]/1024**2:>9.1f} MB  {k}")

sizes.sort()
print()
print("SIZE DISTRIBUTION  (a real photo is rarely under ~100 KB)")
print("-" * 68)
buckets = [(0, 50), (50, 100), (100, 250), (250, 500), (500, 1024),
           (1024, 5120), (5120, 10**9)]
for lo, hi in buckets:
    sel = [s for s, _ in sizes if lo * 1024 <= s < hi * 1024]
    label = f"{lo}-{hi} KB" if hi < 10**9 else f"{lo}+ KB"
    print(f"  {label:<14} {len(sel):>7,}  {sum(sel)/1024**2:>9.1f} MB")

print()
print("LARGEST")
print("-" * 68)
for s, p in sizes[-12:][::-1]:
    print(f"  {s/1024**2:>8.1f} MB  {BS.join(p.split(BS)[-2:])[:60]}")
