r"""Prove the cloud copy by READING IT BACK through the mount, and hashing.

    python verify_drive_by_mount.py --sample 400
    python verify_drive_by_mount.py --sample 400 --max-mb 40
    python verify_drive_by_mount.py --all            # every file, downloads the library

WHY THIS EXISTS ALONGSIDE verify_drive_md5.py

`verify_drive_md5.py` asks Google for its own `md5Checksum` over the Drive API.
That is the better check and it needs a token; this machine's Workspace account
has a reauth policy that a non-interactive shell cannot satisfy, so it has not
run since 2026-09-19.

This needs no token at all, because the mount is already authenticated.

WHAT READING THROUGH THE MOUNT ACTUALLY PROVES

Learning 25 warns that writing into a Drive mount proves nothing: the bytes
land in a local cache and upload behind it. Reading is the same coin the other
way up, and the direction matters:

  * a file NOT in the local cache is FETCHED FROM GOOGLE to satisfy the read.
    Hashing it compares Google's bytes against the digest this project computed
    on the bytes it sent. That is a genuine cross-network check.
  * a file that happens to BE cached is read locally and proves only that the
    cache is intact.

So this cannot promise every read crossed the network. What it can say is the
ratio: the cache holds ~171 GB against a 926 GB library, so the great majority
of files cannot be in it, and a throughput of a few hundred KB/s on a local
disk capable of far more is the network being read. **The measured rate is
printed, because it is the evidence for that claim and the reader should judge
it rather than take it.**

A MISMATCH HERE IS SERIOUS AND IS NOT AUTOMATICALLY THE CLOUD'S FAULT

It means the bytes on Drive differ from the digest recorded when they were
sent. That is either a corrupted upload or a corrupted journal, and this tool
deliberately does not guess which: it names the file and stops short of a
verdict it cannot reach.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import random
import sys
import time

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                               # noqa: E402

JOURNAL = os.path.join(P.AUDIT, "h-mirror.csv")
REPORT = os.path.join(P.AUDIT, "DRIVE-MOUNT-VERIFY.csv")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=JOURNAL)
    ap.add_argument("--report", default=REPORT)
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--max-mb", type=float, default=25.0,
                    help="skip files larger than this. A 3 GB video proves the "
                         "same thing as a 3 MB photograph and costs a thousand "
                         "times the bandwidth.")
    ap.add_argument("--all", action="store_true",
                    help="every journalled file, which DOWNLOADS THE LIBRARY")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    rows = []
    with io.open(a.journal, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("outcome") != "written":
                continue
            if len(r.get("md5") or "") != 32:
                continue
            if not (r.get("dest") or "").upper().startswith("H:"):
                continue
            try:
                n = int(r["bytes"])
            except (ValueError, KeyError):
                continue
            if n <= 0:
                continue
            rows.append((r["dest"], n, r["md5"]))
    # One row per destination: the journal appends, so a path re-sent appears twice.
    latest = {}
    for dest, n, m in rows:
        latest[dest.lower()] = (dest, n, m)
    rows = list(latest.values())
    print("journalled files with a digest: {:,}".format(len(rows)))

    cap = a.max_mb * 1024 * 1024
    small = [r for r in rows if r[1] <= cap]
    print("  within --max-mb {:.0f}: {:,}".format(a.max_mb, len(small)))
    if a.all:
        pick = small
    else:
        random.seed(a.seed)
        pick = random.sample(small, min(a.sample, len(small)))
    print("  verifying: {:,}\n".format(len(pick)))

    ok = bad = absent = 0
    out = []
    t0 = time.time()
    read_bytes = 0
    for i, (dest, n, want) in enumerate(pick, 1):
        # PLAIN path on the mount, never \\?\ (learning 59).
        if not os.path.exists(dest):
            absent += 1
            out.append([dest, n, want, "", "absent from the mount"])
            continue
        h = hashlib.md5()
        try:
            with open(dest, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
        except OSError as e:
            absent += 1
            out.append([dest, n, want, "", "unreadable: {}".format(e)])
            continue
        got = h.hexdigest()
        read_bytes += n
        if got == want:
            ok += 1
            out.append([dest, n, want, got, "match"])
        else:
            bad += 1
            out.append([dest, n, want, got, "MISMATCH"])
            print("  MISMATCH {}".format(dest[-78:]))
        if i % 50 == 0:
            el = time.time() - t0
            print("  {:,}/{:,}  {:.1f} MB read  {:.0f} KB/s".format(
                i, len(pick), read_bytes / 1024 ** 2,
                read_bytes / 1024 / max(el, 1e-9)), flush=True)

    el = max(time.time() - t0, 1e-9)
    with io.open(a.report, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["DrivePath", "Bytes", "JournalMd5", "ReadMd5", "Verdict"])
        w.writerows(out)

    print()
    print("verified {:,} files, {:.2f} GB read in {:.0f}s".format(
        ok + bad, read_bytes / 1024 ** 3, el))
    print("  match    : {:,}".format(ok))
    print("  MISMATCH : {:,}".format(bad))
    print("  absent   : {:,}".format(absent))
    print("  throughput: {:.0f} KB/s - judge for yourself whether that is a "
          "local disk or a network".format(read_bytes / 1024 / el))
    print("  report: {}".format(a.report))
    if bad:
        print()
        print("A MISMATCH means Drive's bytes differ from the digest recorded "
              "when they were sent.")
        print("That is a corrupted upload OR a corrupted journal, and which one "
              "is not decidable from here.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
