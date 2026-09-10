r"""Move the library to a bigger drive, and prove the copy before trusting it.

    python migrate_library.py --to E:                 # plan only, writes nothing
    python migrate_library.py --to E: --apply         # copy
    python migrate_library.py --to E: --verify        # hash every file, both sides

WHY THIS EXISTS RATHER THAN robocopy

robocopy would do the copy. It would not do the third step, and the third step
is the whole point: learning 25 in this project is a run that verified 17,102 of
17,102 files against a mount and had compared local bytes with local bytes. So
verification here READS THE DESTINATION'S OWN BYTES and compares them to the
source hash - never a size, never a count, never the same file twice.

WHERE THE SOURCE HASH COMES FROM

lib-hashes.csv already holds a blake2b-256 for most library files, computed when
they were ingested. Using it is not a shortcut, it is strictly stronger: a fresh
read of both sides proves the copy succeeded, while comparing against the stored
hash proves the copy succeeded AND that the source has not rotted since it was
written - on a drive that has logged controller errors, that is the question
worth asking. Where the cache has no entry, the source is read now.

THE SOURCE IS NEVER TOUCHED. Not moved, not deleted, not modified. It remains a
complete second copy until a human decides otherwise, which - after this runs -
is the first time this library has had two copies at all.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import sys
import time

sys.path.insert(0, r"D:\_PhotoAudit\scripts")
import paths as P                                                # noqa: E402

CHUNK = 8 * 1024 * 1024
HASHES = os.path.join(P.AUDIT, "lib-hashes.csv")


def lp(p: str) -> str:
    return p if p.startswith("\\?\\") else "\\?\\" + p


def load_hashes() -> dict:
    h = {}
    if os.path.exists(HASHES):
        with open(HASHES, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.reader(f):
                if len(row) == 3:
                    try:
                        h[(row[0], int(row[1]))] = row[2]
                    except ValueError:
                        pass
    return h


def blake(path: str) -> str | None:
    try:
        d = hashlib.blake2b(digest_size=32)
        with open(lp(path), "rb", buffering=0) as f:
            for b in iter(lambda: f.read(CHUNK), b""):
                d.update(b)
        return d.hexdigest()
    except OSError:
        return None


def walk(root: str):
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                yield p, os.path.getsize(lp(p))
            except OSError:
                continue


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True, help="target drive, e.g. E:")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    src = P.ROOT
    dst = os.path.join(a.to + os.sep, os.path.basename(src))
    if not os.path.isdir(a.to + os.sep):
        sys.exit(f"{a.to} is not mounted")
    if os.path.abspath(src).lower().startswith(a.to.lower()):
        sys.exit("source and target are the same volume")

    files = list(walk(src))
    total = sum(s for _, s in files)
    free = shutil.disk_usage(a.to + os.sep).free
    print(f"source : {src}")
    print(f"target : {dst}")
    print(f"files  : {len(files):,}   {total/1024**3:.1f} GB")
    print(f"target free: {free/1024**3:.1f} GB "
          f"({'enough' if free > total * 1.02 else 'NOT ENOUGH'})")
    if free <= total * 1.02:
        sys.exit("target does not have room for the library plus 2% slack")

    if not (a.apply or a.verify):
        print("\nplan only. --apply to copy, --verify to prove it.")
        return

    if a.apply:
        done = 0
        t0 = time.time()
        for i, (p, sz) in enumerate(files, 1):
            rel = os.path.relpath(p, src)
            d = os.path.join(dst, rel)
            try:
                if os.path.exists(lp(d)) and os.path.getsize(lp(d)) == sz:
                    done += sz
                    continue                      # resumable: already there
            except OSError:
                pass
            os.makedirs(lp(os.path.dirname(d)), exist_ok=True)
            try:
                shutil.copy2(lp(p), lp(d))
            except OSError as e:
                print(f"  copy failed {rel[:60]}: {e}", flush=True)
                continue
            done += sz
            if i % 500 == 0:
                el = time.time() - t0
                rate = done / max(el, 1) / 1024**2
                left = (total - done) / 1024**2 / max(rate, 0.1) / 60
                print(f"  {i:,}/{len(files):,}  {done/1024**3:.0f} GB  "
                      f"{rate:.0f} MB/s  ~{left:.0f} min left", flush=True)
        print(f"\ncopy finished in {(time.time()-t0)/60:.0f} min")

    if a.verify:
        cache = load_hashes()
        out = os.path.join(P.AUDIT, "MIGRATION-VERIFY.csv")
        ok = bad = missing = 0
        t0 = time.time()
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Source", "Target", "Bytes", "Verdict", "SourceHash",
                        "TargetHash", "HashFrom"])
            for i, (p, sz) in enumerate(files, 1):
                rel = os.path.relpath(p, src)
                d = os.path.join(dst, rel)
                if not os.path.exists(lp(d)):
                    w.writerow([p, d, sz, "MISSING", "", "", ""])
                    missing += 1
                    continue
                sh = cache.get((p, sz))
                where = "cache"
                if not sh:
                    sh = blake(p)
                    where = "read-source"
                th = blake(d)                     # always a fresh read of the copy
                v = "OK" if (sh and th and sh == th) else "MISMATCH"
                if v == "OK":
                    ok += 1
                else:
                    bad += 1
                    w.writerow([p, d, sz, v, sh or "", th or "", where])
                if i % 500 == 0:
                    print(f"  verified {i:,}/{len(files):,}  ok={ok:,} "
                          f"bad={bad} missing={missing}", flush=True)
        print(f"\nverified in {(time.time()-t0)/60:.0f} min")
        print(f"  OK       {ok:,}")
        print(f"  MISMATCH {bad:,}")
        print(f"  MISSING  {missing:,}")
        print(f"  detail   {out}")
        if bad or missing:
            sys.exit("VERIFICATION FAILED - do not repoint paths.py, do not "
                     "touch the source")
        print("\nEvery file proved by reading the copy's own bytes.")
        print("Now, and only now: change ROOT in paths.py to "
              f"{dst}, and leave the source exactly as it is.")


if __name__ == "__main__":
    main()
