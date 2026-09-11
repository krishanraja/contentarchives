r"""Act on the three identified free wins, and list the largest files for review.

Each deletion here is user-directed and specific - a named file the user has
inspected or identified, not a rule-driven sweep. Every action is journalled to
D:\_PhotoAudit\user-directed-deletions.csv with the reason and the evidence.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import sys

AUDIT = r"D:\_PhotoAudit"
LOG = os.path.join(AUDIT, "user-directed-deletions.csv")
MANIFEST = r"D:\ContentLibrary\_Catalog\manifest.csv"

SPIDER = r"D:\ContentLibrary\Media\NoDate\Spider-Man_ No Way Home(2021)..mp4"
DUPE_KEEP = r"D:\ContentLibrary\Media\Pending-Segmentation\2026\2026-02\20260205_165928.mp4"
DUPE_DROP = r"D:\ContentLibrary\Media\Pending-Segmentation\2026\2026-02\20260205_165928__1.mp4"


def journal(path, size, reason, evidence):
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["Path", "Bytes", "Reason", "Evidence", "When"])
        w.writerow([path, size, reason, evidence, dt.datetime.now().isoformat(timespec="seconds")])


def provenance(path):
    """Where did this library file come from?"""
    try:
        with open(MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
            for r in csv.reader(f):
                if r and r[0] == path:
                    return r[1] if len(r) > 1 else "?"
    except OSError:
        pass
    return "(not in manifest)"


print("PROVENANCE OF THE DUPLICATE PAIR")
print("-" * 74)
for p in (DUPE_KEEP, DUPE_DROP):
    print(f"  {os.path.basename(p)}")
    print(f"     from: {provenance(p)[:88]}")

# --- 1. Spider-Man: a commercial feature film, user-directed removal ---------
print()
print("ACTIONS")
print("-" * 74)
if os.path.exists(SPIDER):
    sz = os.path.getsize(SPIDER)
    journal(SPIDER, sz, "user-directed: commercial feature film, not personal media",
            "1920x1080, 116.9 min, identified by title")
    os.remove(SPIDER)
    print(f"  DELETED  {sz/1024**3:.2f} GB  Spider-Man (commercial film)")
else:
    print("  Spider-Man already gone")

# --- 2. The re-muxed duplicate ----------------------------------------------
if os.path.exists(DUPE_KEEP) and os.path.exists(DUPE_DROP):
    a, b = os.path.getsize(DUPE_KEEP), os.path.getsize(DUPE_DROP)
    if a != b:
        print(f"  SKIPPED duplicate: sizes differ ({a:,} vs {b:,}) - not the same recording")
    else:
        journal(DUPE_DROP, b,
                "user-directed: same recording as sibling, re-muxed so byte-different",
                f"identical size {b}, identical duration 1221.783583s, identical creation_time; "
                f"sibling retained at {DUPE_KEEP}")
        os.remove(DUPE_DROP)
        print(f"  DELETED  {b/1024**3:.2f} GB  duplicate recording (sibling retained)")
else:
    print("  duplicate pair not both present - nothing done")

print()
print(f"  journal: {LOG}")
