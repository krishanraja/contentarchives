r"""Act on the three identified free wins, and list the largest files for review.

Each deletion here is user-directed and specific - a named file Krish inspected
or identified, not a rule-driven sweep. Every action is journalled to
D:\_PhotoAudit\user-directed-deletions.csv with the reason and the evidence.

SPENT: both targets were removed on 2026-09-11, so a run now prints "already
gone". Kept for the journal it wrote and the argument it makes about naming a
file rather than matching a rule.

TWO THINGS WERE WRONG WITH HOW IT WAS WRITTEN, fixed on 2026-09-16:

  1. NO DRY RUN. It called os.remove unconditionally - no --apply, no report
     mode. Its sibling clear_scratch.py gates every deletion behind
     `apply = "--apply" in sys.argv`; this one did not, so there was no way to
     ask it what it would do. A script that deletes should be runnable in a mode
     that deletes nothing.

  2. NO __main__ GUARD, so the whole body - including both os.remove calls - ran
     at IMPORT. `import free_wins` deleted a file. That is why
     tests/test_imports.py refuses to import the unguarded list rather than
     sweeping it, and why a deleting script must never be in that list: the
     safety net had to be written around this file instead of over it.

Deletion is the one irreversible thing here, so it gets the rigour (learning 1).
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
        w.writerow([path, size, reason, evidence,
                    dt.datetime.now().isoformat(timespec="seconds")])
        f.flush()
        os.fsync(f.fileno())          # the row lands before the file goes (18)


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


def main() -> None:
    apply = "--apply" in sys.argv

    print("PROVENANCE OF THE DUPLICATE PAIR")
    print("-" * 74)
    for p in (DUPE_KEEP, DUPE_DROP):
        print(f"  {os.path.basename(p)}")
        print(f"     from: {provenance(p)[:88]}")

    # --- 1. Spider-Man: a commercial feature film, user-directed removal -----
    print()
    print("ACTIONS" if apply else "ACTIONS (dry run)")
    print("-" * 74)
    if os.path.exists(SPIDER):
        sz = os.path.getsize(SPIDER)
        if apply:
            journal(SPIDER, sz,
                    "user-directed: commercial feature film, not personal media",
                    "1920x1080, 116.9 min, identified by title")
            os.remove(SPIDER)
            print(f"  DELETED  {sz/1024**3:.2f} GB  Spider-Man (commercial film)")
        else:
            print(f"  would delete  {sz/1024**3:.2f} GB  Spider-Man (commercial film)")
    else:
        print("  Spider-Man already gone")

    # --- 2. The re-muxed duplicate -------------------------------------------
    if os.path.exists(DUPE_KEEP) and os.path.exists(DUPE_DROP):
        a, b = os.path.getsize(DUPE_KEEP), os.path.getsize(DUPE_DROP)
        if a != b:
            print(f"  SKIPPED duplicate: sizes differ ({a:,} vs {b:,}) - "
                  f"not the same recording")
        elif apply:
            journal(DUPE_DROP, b,
                    "user-directed: same recording as sibling, re-muxed so byte-different",
                    f"identical size {b}, identical duration 1221.783583s, "
                    f"identical creation_time; sibling retained at {DUPE_KEEP}")
            os.remove(DUPE_DROP)
            print(f"  DELETED  {b/1024**3:.2f} GB  duplicate recording (sibling retained)")
        else:
            print(f"  would delete  {b/1024**3:.2f} GB  duplicate recording "
                  f"(sibling retained)")
    else:
        print("  duplicate pair not both present - nothing done")

    print()
    print(f"  journal: {LOG}")
    if not apply:
        print("  DRY RUN - nothing was deleted. Re-run with --apply.")


if __name__ == "__main__":
    main()
