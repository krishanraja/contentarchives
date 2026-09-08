r"""Delete byte-identical copies that exist more than once outside the library.

The laptop backups overlap heavily - the same file captured by two or three
different backup runs. The space audit found these by hashing size-collisions; this
acts on that list.

It does NOT trust that list. It was computed before tonight's deletions, so some
entries are already gone and others may have changed. Every pair is re-verified by
whole-file hash at the moment of deletion:

  - the keeper must still exist
  - the redundant copy must still exist
  - both must still hash identically
  - neither may be inside the library

Any pair failing those checks is skipped and reported, never deleted on the strength
of a stale record.

    python purge_redundant.py            # report
    python purge_redundant.py --apply
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import sys

SRC = r"D:\_PhotoAudit\SPACE-TIERS.csv"
JOURNAL = r"D:\_PhotoAudit\user-directed-deletions.csv"
PROTECTED = [r"D:\ContentLibrary", r"D:\ContentLibrary\ContentProduction"]


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def protected(path: str) -> bool:
    low = os.path.abspath(path).lower()
    return any(low.startswith(p.lower() + "\\") for p in PROTECTED)


def file_hash(path: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    with open(lp(path), "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def journal_one(path: str, size: int, keep: str) -> None:
    """Append one deletion record and flush it to disk immediately."""
    new = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["Path", "Bytes", "Reason", "Evidence", "When"])
        w.writerow([path, size,
                    "user-directed: byte-identical copy, one retained",
                    f"whole-file hash match, re-verified at deletion; retained: {keep}",
                    dt.datetime.now().isoformat(timespec="seconds")])
        f.flush()
        os.fsync(f.fileno())


def main() -> None:
    apply = "--apply" in sys.argv
    if not os.path.exists(SRC):
        sys.exit(f"missing {SRC} - run space_tiers.py first")

    pairs = []
    with open(SRC, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            if r["Tier"] == "2-redundant" and r.get("DuplicateOf"):
                pairs.append((int(r["Bytes"]), r["Path"], r["DuplicateOf"]))
    pairs.sort(reverse=True)
    print(f"{len(pairs):,} candidate pairs, "
          f"{sum(p[0] for p in pairs)/1024**3:.2f} GB")

    deleted, freed = [], 0
    skipped = {"gone": 0, "keeper-gone": 0, "changed": 0, "protected": 0}

    for i, (size, extra, keep) in enumerate(pairs, 1):
        if i % 100 == 0:
            print(f"  {i:,}/{len(pairs):,}  freed {freed/1024**3:.2f} GB", flush=True)

        if protected(extra) or protected(keep):
            skipped["protected"] += 1
            continue
        if not os.path.exists(lp(extra)):
            skipped["gone"] += 1
            continue
        if not os.path.exists(lp(keep)):
            # the copy we intended to keep is gone; the "redundant" one is now
            # the only copy. Keeping it is the whole point.
            skipped["keeper-gone"] += 1
            continue
        try:
            if file_hash(extra) != file_hash(keep):
                skipped["changed"] += 1
                continue
        except OSError:
            skipped["changed"] += 1
            continue

        if not apply:
            freed += size
            deleted.append((extra, size, keep))
            continue

        # Journal BEFORE deleting, and flush. A record written afterwards is
        # lost precisely when it matters most - a crash or a kill mid-run leaves
        # files gone with nothing saying what they were. An entry for a deletion
        # that then fails is a harmless over-record; the reverse is not.
        journal_one(extra, size, keep)
        try:
            try:
                os.remove(lp(extra))
            except PermissionError:
                os.chmod(lp(extra), 0o666)
                os.remove(lp(extra))
            deleted.append((extra, size, keep))
            freed += size
        except OSError as e:
            print(f"  FAILED {extra}: {e}")

    print()
    print("REPORT ONLY - re-run with --apply" if not apply else "APPLIED")
    print("-" * 66)
    print(f"  {'removed' if apply else 'would remove'}: {len(deleted):,} files, "
          f"{freed/1024**3:.2f} GB")
    for k, v in skipped.items():
        if v:
            print(f"  skipped ({k}): {v:,}")
    if apply:
        print(f"  journal: {JOURNAL}")


if __name__ == "__main__":
    main()
