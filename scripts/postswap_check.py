r"""After the drive letters are swapped: prove the new disk really is the library.

    python postswap_check.py

Run this immediately after the swap and before anything writes. The swap is the
one step in the migration with no undo and no error message: every path in the
toolkit is `D:\...`, so if the wrong disk answers to D: the tools do not fail,
they quietly operate on the wrong drive. Ten seconds of checking beats finding
out from an ingest.

Every check names what it read. Nothing here is inferred from a document.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

FAILED = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"         {detail}")
    if not ok:
        FAILED.append(name)


def count(root: str) -> int:
    n = 0
    for _, _, fns in os.walk(root):
        n += len(fns)
    return n


def main() -> None:
    print("POST-SWAP CHECK")
    print("=" * 74)

    vol = os.path.splitdrive(P.ROOT)[0] + os.sep

    # 1. Is the disk behind D: the big one? The whole point of the migration.
    try:
        total = shutil.disk_usage(vol).total / 1024 ** 3
    except OSError as e:
        check("the library volume is mounted", False, str(e))
        total = 0
    check("the library volume is the new, larger disk", total > 2000,
          f"{vol} is {total:,.1f} GB "
          f"({'the LaCie' if total > 2000 else 'NOT the new disk - this is the old drive'})")

    # 2. The layout paths.py defines actually exists on it.
    trees = {"Personal": P.PERSONAL, "Communal": P.COMMUNAL,
             "NoDate": P.NODATE, "Pending-Segmentation": P.PENDING}
    absent = [k for k, v in trees.items() if not os.path.isdir(v)]
    check("every chronology tree exists under the new root", not absent,
          f"{P.ROOT} " + ("has all four" if not absent else f"MISSING {absent}"))

    # 3. The file count matches what was copied. MIGRATION-HASHES.csv has one
    #    row per file the migration read, which is an independent record of what
    #    should be here - not a restatement of it.
    mig = os.path.join(P.AUDIT, "MIGRATION-HASHES.csv")
    if os.path.exists(mig):
        with open(mig, newline="", encoding="utf-8", errors="replace") as f:
            expected = sum(1 for r in csv.reader(f) if r)
        actual = count(P.ROOT)
        drift = abs(actual - expected)
        check("library file count matches the migration record",
              drift <= max(5, expected * 0.0005),
              f"migration recorded {expected:,}, on disk {actual:,}, drift {drift:,}")
    else:
        check("migration record present", False, f"{mig} not found")

    # 4. The audit trail came across. Without it nothing is resumable.
    need = ["autopilot-added.csv", "autopilot-duplicates.csv", "lib-hashes.csv",
            "H-ROUTING.csv", "STATE.json"]
    gone = [n for n in need if not os.path.exists(os.path.join(P.AUDIT, n))]
    check("the audit trail is on the new volume", not gone,
          f"{P.AUDIT} " + ("has the journals" if not gone else f"MISSING {gone}"))

    # 5. The journals point at files that exist. They store absolute D: paths
    #    written before the swap; those must now resolve on the new disk.
    added = os.path.join(P.AUDIT, "autopilot-added.csv")
    if os.path.exists(added):
        with open(added, newline="", encoding="utf-8", errors="replace") as f:
            rows = [r[0] for r in csv.reader(f) if r]
        # The TAIL, deliberately. A placement recorded early in the project
        # has usually been moved since - by the restructure, by the _Review
        # eviction, by the restore that put 9,975 files back - so an even
        # sample across the whole journal resolves at 13% ON A HEALTHY DRIVE
        # and would fail this check every time. The last 2,000 placements are
        # this week's ingest, nothing has moved them, and they resolve at
        # 100%. Measured both ways on 2026-09-11 before trusting either.
        sample = rows[-2000:]
        miss = [d for d in sample if not os.path.exists(d)]
        check("recent journalled destinations resolve on the new volume",
              len(miss) <= len(sample) * 0.01,
              f"sampled the last {len(sample):,} of {len(rows):,} placements, "
              f"{len(miss)} do not exist")

    # 6. The resume set still works, so the remaining ingest will not re-pull.
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ifh", os.path.join(P.SCRIPTS, "ingest_from_h.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        h = m.handled_from_stage()
        check("the H: resume set rebuilds", len(h) > 3000,
              f"{len(h):,} files recorded as already through the pipeline")
    except Exception as e:                                       # noqa: BLE001
        check("the H: resume set rebuilds", False, str(e)[:160])

    # 7. The old drive still holds the second copy. The migration is only worth
    #    something if this is true, and it is the easiest thing to lose track of.
    others = [d + ":" + os.sep for d in "EFGHIJ"
              if os.path.isdir(d + ":" + os.sep) and d + ":" != os.path.splitdrive(P.ROOT)[0]]
    second = [o for o in others if os.path.isdir(os.path.join(o, "ContentLibrary"))]
    check("a second copy of the library exists on another volume", bool(second),
          f"found at {second}" if second else
          "NO SECOND COPY FOUND - do not delete anything from any drive")

    # 8. State regenerates against the new root rather than reporting zero.
    st = os.path.join(P.AUDIT, "STATE.json")
    if os.path.exists(st):
        try:
            d = json.load(open(st, encoding="utf-8"))
            tot = d["library"]["total_files"]
            check("STATE.json carries a non-zero library count", tot > 0,
                  f"{tot:,} files (regenerate with track.py after the swap)")
        except Exception as e:                                   # noqa: BLE001
            check("STATE.json readable", False, str(e)[:120])

    print("=" * 74)
    if FAILED:
        print(f"  {len(FAILED)} of the checks failed:")
        for n in FAILED:
            print(f"    - {n}")
        print()
        print("  Do not run the ingest and do not delete anything until these")
        print("  are understood. A wrong answer here means the tools are")
        print("  pointed at the wrong disk, which nothing else will tell you.")
        sys.exit(1)
    print("  All checks passed. The new volume is the library.")
    print("  Next: python track.py, then resume the H: ingest.")


if __name__ == "__main__":
    main()
