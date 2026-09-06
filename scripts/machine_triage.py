r"""Triage the batch transferred from the second machine before ingesting any of it.

The transfer list was built by extension, so it swept up every PNG on the machine.
Most of that turns out to be software project output - QA screenshots, prerendered
UI, audit evidence - which does not belong in a personal photo library and would
make the later personal/communal split harder, not easier.

Nothing is deleted here. This only sorts the list into buckets and reports them.
"""

from __future__ import annotations

import csv
import os
import re

LOG = r"G:\My Drive\_photo-consolidation\out\machine-b-copy-log.csv"
OUT = r"D:\_PhotoAudit\machine-b-TRIAGE.csv"

# Filenames a camera or phone assigns itself.
CAMERA = re.compile(
    r"^(IMG[_-]|MVI_|DSC|DSCN|PXL_|VID[_-]|GOPR|GX\d|GH\d|DJI[_-]"
    r"|\d{8}[_-]\d{6}|PANO|BURST|WhatsApp|Screenshot_2\d)", re.I)

# Directories that mean "this is software work", not "this is a memory".
DEV_DIR = re.compile(
    r"[\\/](shots|screenshots|\.prerender|profile|prototypes|evidence"
    r"|_audit|audit|qa|chronicle-shots|gutted|dev|node_modules|dist|build)[\\/]",
    re.I)
DEV_PROJECT = re.compile(
    r"[\\/](PROJECT-A-Apps|cc-uxtest|circle-qa|ctrl-corpus|mm-ctrl"
    r"|PROJECT-B[-\w]*|fleet-sweep|closure-day1|full-time|codex)[\\/]", re.I)

MEDIA_EXT = {".mp4", ".mov", ".webm", ".heic", ".jpg", ".jpeg"}


def bucket(path: str) -> str:
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    if CAMERA.match(base):
        return "media"                       # camera-original: always media
    if DEV_DIR.search(path) or DEV_PROJECT.search(path):
        return "dev"
    if ext == ".png":
        return "dev"                         # PNG off a dev machine is a screenshot
    if ext in MEDIA_EXT:
        return "media"
    return "unclear"


def main() -> None:
    rows = []
    with open(LOG, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if len(r) >= 2:
                rows.append((r[0], int(r[1])))

    counts: dict[str, list] = {"media": [], "dev": [], "unclear": []}
    for p, s in rows:
        counts[bucket(p)].append((p, s))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Bucket", "OriginalPath", "Bytes"])
        for b, items in counts.items():
            for p, s in items:
                w.writerow([b, p, s])

    print(f"{len(rows):,} files, {sum(s for _, s in rows)/1024**3:.2f} GB")
    print()
    for b in ("media", "unclear", "dev"):
        items = counts[b]
        print(f"{b:>8}: {len(items):>5,} files  {sum(s for _, s in items)/1024**2:>9.1f} MB")

    for b in ("media", "unclear"):
        print()
        print(f"LARGEST IN '{b}'")
        print("-" * 96)
        for p, s in sorted(counts[b], key=lambda x: -x[1])[:20]:
            print(f"  {s/1024**2:>8.1f} MB  {p}")

    print()
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
