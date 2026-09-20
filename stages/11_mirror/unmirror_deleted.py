r"""Remove from Drive the copies the library no longer holds.

    python unmirror_deleted.py --list "D:\_PhotoAudit\DRIVE-DEDUPE-VICTIMS.csv"
    python unmirror_deleted.py --list ... --apply

The mirror only ever ADDS. After the library was deduped on 2026-09-20 it held
81,449 files and Drive still held 82,685 - the 1,236 removed copies survived in
the cloud because nothing in this repo could take them out. Krish: *"Clean the
1236."*

WHY THIS DOES NOT RE-HASH, AND WHY THAT IS NOT A WEAKENING

`guarded_delete` re-hashes both files at the unlink, which is right on a local
disk and wrong here: every read of a Drive path hydrates the placeholder and
downloads the bytes (learning 5). Hashing 1,236 victims and their keepers would
pull ~40 GB through the cache that deadlocked the mirror overnight, to re-prove
something already proven twice:

  1. `dedupe_library.py` re-hashed the D: victim against the D: keeper at the
     instant it deleted the victim. They were byte-identical.
  2. `verify_drive_md5.py` matched BOTH D: files against the md5 Google computed
     on receipt, 82,681 of 82,681.

So the Drive victim and the Drive keeper hold identical content by transitivity,
and the chain is recorded rather than assumed. What this checks instead, per
file and at the moment of deletion:

  - the KEEPER still exists on Drive. A victim is never removed while its
    survivor is absent, whatever a list says.
  - the victim's size still matches what the mirror journal recorded when it
    uploaded it. Size is not identity (learnings 22, 36) - here it is a guard
    against deleting a path that has since been overwritten by something else.

PLAIN PATHS, NOT \\?\. On the DriveFS mount the long-path prefix is what breaks
things (learning 59), and PowerShell's Remove-Item is refused outright on
`H:\My Drive` - a refusal that aborts the whole call. Python's os.remove on a
plain path is the one route proven to work here.

THIS SENDS FILES TO DRIVE'S TRASH, where they sit for 30 days and count against
the quota. A permanent delete needs the Drive API and a live token.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402

JOURNAL = os.path.join(P.AUDIT, "DRIVE-UNMIRRORED.csv")

csv.field_size_limit(1 << 30)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", required=True,
                    help="CSV of DriveVictim,Bytes,DriveKeeper,Hash")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-seconds", type=float, default=420.0)
    a = ap.parse_args()

    rows = list(csv.DictReader(io.open(a.list, encoding="utf-8", newline="")))
    if not rows:
        print("the list names nothing")
        return 1

    done = set()
    if os.path.exists(JOURNAL):
        for r in csv.DictReader(io.open(JOURNAL, encoding="utf-8", newline="")):
            if r.get("Removed"):
                done.add(r["Removed"].lower())
        if done:
            print("resuming, already removed: {:,}".format(len(done)))

    todo = [r for r in rows if r["DriveVictim"].lower() not in done]
    print("copies to remove from Drive: {:,}".format(len(todo)))
    print("bytes they occupy          : {:.2f} GB".format(
        sum(int(r.get("Bytes") or 0) for r in todo) / (1 << 30)))
    print()

    if not a.apply:
        for r in todo[:6]:
            print("  remove {}".format(r["DriveVictim"][-92:]))
            print("    keeper {}".format(r["DriveKeeper"][-88:]))
        print()
        print("DRY RUN - nothing touched. Re-run with --apply.")
        return 0

    fresh = not os.path.exists(JOURNAL)
    fh = io.open(JOURNAL, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if fresh:
        w.writerow(["Removed", "Bytes", "Keeper", "Hash", "When"])

    t0 = time.time()
    gone = kept = missing = wrong = 0
    freed = 0
    try:
        for r in todo:
            if time.time() - t0 > a.max_seconds:
                break
            victim, keeper = r["DriveVictim"], r["DriveKeeper"]

            if not os.path.exists(keeper):
                kept += 1                      # survivor absent: refuse
                continue
            if not os.path.exists(victim):
                missing += 1                   # already gone
                w.writerow([victim, r.get("Bytes"), keeper, r.get("Hash"),
                            time.strftime("%Y-%m-%dT%H:%M:%S")])
                continue
            try:
                size = os.path.getsize(victim)
            except OSError:
                missing += 1
                continue
            want = int(r.get("Bytes") or 0)
            if want and size != want:
                wrong += 1                     # not the file we uploaded
                continue

            try:
                os.remove(victim)
            except OSError as e:
                print("  FAILED {}: {}".format(os.path.basename(victim), e))
                continue
            gone += 1
            freed += size
            w.writerow([victim, size, keeper, r.get("Hash"),
                        time.strftime("%Y-%m-%dT%H:%M:%S")])
            if gone % 100 == 0:
                fh.flush()
                os.fsync(fh.fileno())
                print("  removed {:,}  freed {:.2f} GB".format(
                    gone, freed / (1 << 30)), flush=True)
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    print()
    print("removed from Drive : {:,}  ({:.2f} GB)".format(
        gone, freed / (1 << 30)))
    print("already gone       : {:,}".format(missing))
    print("REFUSED, keeper absent on Drive : {:,}".format(kept))
    print("REFUSED, size no longer matches : {:,}".format(wrong))
    print()
    print("These are in Drive's TRASH for 30 days and still count against the")
    print("quota. Empty it, or delete permanently with a live Drive token.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
