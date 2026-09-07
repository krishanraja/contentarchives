r"""Delete Google's degraded re-encodes, keeping the original the library holds.

Google Photos returns "Storage saver" copies of media uploaded at full quality.
They are not byte-identical to the originals, so the content-hash dedup files
them as new and the library gains a worse copy of a photo it already had.
Measured across the 2026-09-07 export: 6,217 files, 14.77 GB, quality gaps
reaching 66.8x - a 1.4 MB clip against a 90.2 MB original.

This deletes the degraded copy. `triage_downgrades.py` MOVES them to `_Review\`,
which is the right default; moving frees no space because `_Review\` is on the
same volume, so when the drive is the constraint they have to actually go.

EVERY DELETION IS RE-VERIFIED AT THE MOMENT IT HAPPENS.

The triage report is a snapshot, and the library changes underneath it - an
ingest was still running when this report was written. Deleting from a stale
list is how a file that is no longer redundant gets destroyed. So for each row,
immediately before unlinking:

  - the ORIGINAL being kept must still exist
  - it must still be strictly LARGER than the copy being deleted
  - the copy being deleted must still be the size the report recorded

Any row failing any check is skipped and reported, never deleted. This is the
same discipline purge_redundant.py uses, and it exists because a delete
justified by a check that did not actually check is how 45 files were lost.

    python purge_downgrades.py            # dry run
    python purge_downgrades.py --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

AUDIT = r"D:\_PhotoAudit"
REPORT = os.path.join(AUDIT, "DOWNGRADE-TRIAGE-REPORT.csv")
JOURNAL = os.path.join(AUDIT, "user-directed-deletions.csv")


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(REPORT):
        sys.exit(f"no triage report: {REPORT}. Run triage_downgrades.py first.")

    rows = [r for r in csv.DictReader(open(REPORT, encoding="utf-8"))
            if r["Verdict"] == "downgrade-move"]
    print(f"{len(rows):,} candidates in the report")

    ok, skipped, freed = [], [], 0
    for r in rows:
        dead, keep = r["NewFile"], r["HeldFile"]
        try:
            dead_now = os.path.getsize(lp(dead))
        except OSError:
            skipped.append((dead, "already gone")); continue
        try:
            keep_now = os.path.getsize(lp(keep))
        except OSError:
            skipped.append((dead, "ORIGINAL MISSING - refusing")); continue
        if dead_now != int(r["NewBytes"]):
            skipped.append((dead, f"size changed since report ({dead_now})")); continue
        if keep_now <= dead_now:
            skipped.append((dead, "original no longer larger - refusing")); continue
        ok.append((dead, dead_now, keep, keep_now, r["Ratio"]))
        freed += dead_now

    GB = 1024 ** 3
    print(f"  re-verified, safe to delete : {len(ok):,}  ({freed/GB:.2f} GB)")
    print(f"  skipped                     : {len(skipped):,}")
    for p, why in skipped[:10]:
        print(f"      {why}: {os.path.basename(p)}")

    if not a.apply:
        print("\nDRY RUN - nothing deleted. Re-run with --apply.")
        return

    new_journal = not os.path.exists(JOURNAL)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    deleted = 0
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new_journal:
            w.writerow(["Path", "Bytes", "Reason", "Evidence", "When"])
        for dead, dbytes, keep, kbytes, ratio in ok:
            # last look before the unlink: the original must still be there
            try:
                if os.path.getsize(lp(keep)) != kbytes:
                    skipped.append((dead, "original changed during run")); continue
            except OSError:
                skipped.append((dead, "original vanished during run")); continue
            try:
                os.remove(lp(dead))
            except OSError as e:
                skipped.append((dead, f"delete failed: {e}")); continue
            w.writerow([dead, dbytes,
                        "user-directed: Google Storage-saver re-encode; library holds "
                        "the original at higher quality",
                        f"kept {keep} at {kbytes:,} bytes, {ratio}x larger", stamp])
            deleted += 1
        jf.flush()
        os.fsync(jf.fileno())

    print(f"\ndeleted {deleted:,} files, freed {freed/GB:.2f} GB")
    print(f"journalled to {JOURNAL} - check_manifest reads this, so the manifest")
    print("rows they leave behind are accounted for rather than reported as losses.")


if __name__ == "__main__":
    main()
