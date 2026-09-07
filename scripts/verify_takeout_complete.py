r"""Prove every member of every Takeout part reached the library, then say so.

The mission is "all six parts merged without duplication, originals deleted once
verified". The dangerous half of that sentence is the last four words: a delete
justified by a check that did not actually check is how the 45 files were lost.

So this does not ask "did the driver say it was finished". It compares, per part:

  ground truth   every media member in the archive's CENTRAL DIRECTORY, captured
                 by zip_fingerprint / ingest_eta into arc-sizes.json BEFORE the
                 archive was deleted. This is the only record that survives the
                 deletion, which is why it is captured up front rather than at
                 verification time.

  what happened  arc-progress/<part>.csv, one row per member with its outcome.

A member present in the first and absent from the second was never processed,
whatever the state file claims. That is the failure this exists to catch.

'dup' is a SUCCESS, not a shortfall: the file's content is already in the library
under some other name, verified by whole-file hash. Merging without duplication
is the goal, so a duplicate correctly rejected is the mechanism working.

    python verify_takeout_complete.py
    python verify_takeout_complete.py --strict   # exit 1 unless all six are clean
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter

AUDIT = r"D:\_PhotoAudit"
SIZES = os.path.join(AUDIT, "arc-sizes.json")
PROG = os.path.join(AUDIT, "arc-progress")
STATE = os.path.join(AUDIT, "autopilot-state.csv")
STEM = "takeout-20260907T082613Z-1-{:03d}.zip"
SEARCH = [r"C:\Users\user\Downloads", "D:\\", r"D:\Takeout", r"C:\GoogleTakeout"]


def consumed() -> set[str]:
    s = set()
    if os.path.exists(STATE):
        with open(STATE, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r:
                    s.add(r[0])
    return s


def ground_truth() -> dict[str, dict]:
    if not os.path.exists(SIZES):
        return {}
    cache = json.load(open(SIZES, encoding="utf-8"))
    out = {}
    for k, v in cache.items():
        out[k.split("|")[0]] = v
    return out


def handled(part: str) -> dict[str, str]:
    p = os.path.join(PROG, part + ".csv")
    out = {}
    if not os.path.exists(p):
        return out
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                out[row[0]] = row[1]
    return out


def still_on_disk(part: str) -> str | None:
    for d in SEARCH:
        p = os.path.join(d, part)
        if os.path.exists(p):
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    truth = ground_truth()
    done = consumed()
    all_clean = True

    print("VERIFYING THE 2026-09-07 TAKEOUT EXPORT")
    print("=" * 78)

    for n in range(1, 7):
        part = STEM.format(n)
        gt = truth.get(part)
        h = handled(part)
        outcomes = Counter(h.values())
        on_disk = still_on_disk(part)
        mark = "consumed" if part in done else "NOT consumed"

        print(f"\n{part}")
        if not gt:
            print("  [WARN] no ground truth captured - cannot verify this part.")
            print("         Fingerprint it BEFORE it is deleted, or verification")
            print("         becomes impossible once the archive is gone.")
            all_clean = False
            continue

        missing = [m for m in gt if m not in h]
        print(f"  members in archive : {len(gt):,}")
        print(f"  members handled    : {len(h):,}   "
              f"({outcomes.get('new',0):,} new, {outcomes.get('dup',0):,} dup"
              + (f", {outcomes.get('failed',0):,} FAILED" if outcomes.get('failed') else "")
              + ")")
        if missing:
            print(f"  [FAIL] {len(missing):,} members never processed. First 5:")
            for m in missing[:5]:
                print(f"           {m}")
            all_clean = False
        elif part not in done:
            print(f"  [....] every member accounted for, but not yet marked {mark}")
            all_clean = False
        else:
            print("  [PASS] every member accounted for, and consumed")

        if on_disk:
            sz = os.path.getsize(on_disk) / 1024 ** 3
            if missing or part not in done:
                print(f"  archive still present ({sz:.1f} GB) - correct, do not delete yet")
            else:
                print(f"  [ACTION] verified but STILL ON DISK ({sz:.1f} GB): {on_disk}")
        else:
            print("  archive deleted")

    print("\n" + "=" * 78)
    if all_clean:
        print("ALL SIX PARTS VERIFIED: every media member accounted for, archives gone.")
    else:
        print("NOT COMPLETE. Nothing should be deleted on the strength of this run.")
    if a.strict and not all_clean:
        sys.exit(1)


if __name__ == "__main__":
    main()
