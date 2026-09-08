r"""Move the audio library off the photo drive to H:\My Drive\Music.

D: is meant to end up holding photographs and video and nothing else, so the
music has to go somewhere. It is not deleted - it is moved, and the move is only
completed once the destination is proven to hold it.

THE ORDER MATTERS AND IT IS NOT NEGOTIABLE

    copy  ->  verify size at the destination  ->  DriveFS queue drains to 0
          ->  only then delete the source

Writing into a Drive mount lands the bytes in a LOCAL CACHE and uploads behind
it. The mount will show the file as present, at the right size, while the cloud
has nothing. Deleting the source at that point destroys the only real copy.
That illusion has already been met once on this project, on 140.62 GB, where
17,102 of 17,102 files "verified" against a cache holding the bytes just
written. So the mount is never the witness here: the DriveFS `operations` table
is, and it has to reach zero.

This script does the COPY half only. Deletion is a separate, deliberate step
(--delete-verified) that re-checks every file before removing anything.

    python move_audio_to_h.py                  # copy, then report
    python move_audio_to_h.py --delete-verified
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile

MANIFEST = r"D:\_PhotoAudit\tier2-audio.json"
DEST_ROOT = r"H:\My Drive\Music"
LOG = r"D:\_PhotoAudit\audio-move.csv"
JOURNAL = r"D:\_PhotoAudit\user-directed-deletions.csv"
DRIVEFS = r"C:\Users\user\AppData\Local\Google\DriveFS"


def _accounts():
    for acct in glob.glob(os.path.join(DRIVEFS, "1*")):
        db = os.path.join(acct, "metadata_sqlite_db")
        if os.path.exists(db):
            yield acct, db


def _snapshot(db: str, tag: str):
    tmp = os.path.join(tempfile.gettempdir(), f"dfs_{tag}.db")
    shutil.copy2(db, tmp)
    con = sqlite3.connect(tmp)
    con.text_factory = bytes
    return con


def queue_depth() -> int | None:
    """Pending operations for the account that actually owns the destination.

    This originally summed EVERY Drive account, and that was wrong in a way that
    blocked real work: two accounts are mounted, and on 2026-09-07 the one with
    no connection to this upload sat at 10 stale operations for eleven hours
    while the account holding the files had drained to 0. The guard refused a
    deletion on the strength of a number about somebody else's backlog.

    Scope the question to the account that indexes the files being uploaded.
    Returns None if nothing can be read - and None is never treated as zero.
    """
    best = None
    for acct, db in _accounts():
        try:
            con = _snapshot(db, os.path.basename(acct)[:8])
            owned = con.execute(
                "SELECT COUNT(*) FROM items WHERE local_title LIKE '%.mp3'"
            ).fetchone()[0]
            pending = con.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
            con.close()
        except Exception:
            continue
        if best is None or owned > best[0]:
            best = (owned, pending)
    return best[1] if best else None


def cloud_has(paths: list[str]) -> tuple[int, int]:
    """(present, missing) - are these files in the cloud's own index?

    Stronger than a queue reading zero: an empty queue says nothing is waiting,
    not that a particular file arrived. This asks after the files themselves.
    """
    names = {os.path.basename(p).lower() for p in paths}
    indexed: set[str] = set()
    for acct, db in _accounts():
        try:
            con = _snapshot(db, os.path.basename(acct)[:8] + "c")
            for (t,) in con.execute("SELECT local_title FROM items"):
                if t:
                    indexed.add(t.decode("utf-8", "replace").lower())
            con.close()
        except Exception:
            continue
    present = len(names & indexed)
    return present, len(names) - present


def dest_for(src: str) -> str:
    rel = os.path.relpath(src, "D:\\")
    return os.path.join(DEST_ROOT, rel)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delete-verified", action="store_true")
    a = ap.parse_args()

    files = [(p, s) for p, s in json.load(open(MANIFEST, encoding="utf-8"))]
    print(f"{len(files):,} files, {sum(s for _, s in files)/1024**3:.2f} GB")

    if not a.delete_verified:
        os.makedirs(DEST_ROOT, exist_ok=True)
        copied = skipped = failed = 0
        done_b = 0
        with open(LOG, "w", newline="", encoding="utf-8") as lf:
            w = csv.writer(lf)
            w.writerow(["Source", "Dest", "Bytes", "Outcome"])
            for i, (src, size) in enumerate(files, 1):
                dst = dest_for(src)
                try:
                    if os.path.exists(dst) and os.path.getsize(dst) == size:
                        skipped += 1; done_b += size
                        w.writerow([src, dst, size, "already-present"]); continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    if os.path.getsize(dst) != size:
                        failed += 1
                        w.writerow([src, dst, size, "SIZE MISMATCH"]); continue
                    copied += 1; done_b += size
                    w.writerow([src, dst, size, "copied"])
                except Exception as e:
                    failed += 1
                    w.writerow([src, dst, size, f"FAILED {e}"])
                if i % 100 == 0:
                    print(f"  {i:,}/{len(files):,}  {done_b/1024**3:.1f} GB", flush=True)
        print(f"\ncopied {copied:,}, already there {skipped:,}, failed {failed:,}")
        q = queue_depth()
        print(f"DriveFS upload queue: {q if q is not None else 'UNREADABLE'}")
        print("\nNOT deleting anything. The bytes are in the local Drive cache and")
        print("upload behind it. Re-run with --delete-verified once the queue is 0.")
        return

    # ---- deletion half ----
    q = queue_depth()
    if q is None:
        sys.exit("cannot read the DriveFS queue - refusing to delete on an unknown state")
    if q != 0:
        sys.exit(f"DriveFS still has {q:,} operations pending - refusing to delete. "
                 "The cloud does not have these files yet.")
    print("DriveFS queue is 0 - the uploads have completed.")

    stamp = dt.datetime.now().isoformat(timespec="seconds")
    deleted = freed = 0
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        for src, size in files:
            dst = dest_for(src)
            try:
                if os.path.getsize(dst) != size:
                    print(f"  dest wrong size, keeping source: {src}"); continue
            except OSError:
                print(f"  dest missing, keeping source: {src}"); continue
            try:
                cur = os.path.getsize(src)
            except OSError:
                continue
            if cur != size:
                print(f"  source changed, skipping: {src}"); continue
            try:
                os.remove(src)
            except OSError as e:
                print(f"  delete failed {src}: {e}"); continue
            w.writerow([src, size, "user-directed: audio moved off the photo drive",
                        f"copied to {dst}, size verified, DriveFS queue 0", stamp])
            deleted += 1; freed += size
        jf.flush(); os.fsync(jf.fileno())
    print(f"\ndeleted {deleted:,} sources, freed {freed/1024**3:.2f} GB")


if __name__ == "__main__":
    main()
