r"""Delete the source copies the library provably holds - and only those.

    python purge_audited_sources.py --root "E:\"                  # report
    python purge_audited_sources.py --root "E:\" --apply
    python purge_audited_sources.py --root "E:\" --apply --max-seconds 420

Drives `guarded_delete.delete_with_surviving_copy`, which re-hashes BOTH files
at the instant of the unlink, refuses a survivor on the same inode, and journals
the evidence. A report is never evidence here; the filesystem at the moment of
deletion is.

THREE PROOFS BEFORE A BYTE IS REMOVED

  1. THE AUDIT said the library holds this content (SOURCE-AUDIT-*.csv, verdict
     HELD, with the library path it matched).
  2. THE FILESYSTEM agrees, re-read now: same size, same blake2b-256, different
     inode, survivor readable end to end. `guarded_delete` enforces this and
     raises on any doubt.
  3. THE CLOUD has it. This is the one the guard cannot know about on its own,
     and it is the reason this file exists rather than a loop over
     guarded_delete: deleting E: leaves D: as the ONLY local copy, so "the
     library holds it" is not sufficient comfort. `h-mirror.csv` carries both
     blake2b and md5 for every mirrored file, and `drive-listing.jsonl` carries
     the md5 Google computed on receipt. A survivor whose md5 is absent from
     Drive's own listing is NOT proven, and its source copy stays.

Proof 3 also fails safely for anything ingested since the last mirror: those
files are simply not in the journal yet, so their sources are kept until the
mirror and the verification catch up. That is the correct answer, not an error.

SYNC MOUNTS ARE NOT LOCAL DISKS. G:, H: and OneDrive delete to the cloud as
well; the bytes go to a 30-day trash and then they are gone. The journal records
which root each deletion came from so that is never a surprise later.

Resumable in slices, because 1,094 GB across 108,628 files is hours of re-
hashing and this machine kills long jobs.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
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
from guarded_delete import delete_with_surviving_copy, DeletionRefused  # noqa: E402

MIRROR_JOURNAL = os.path.join(P.AUDIT, "h-mirror.csv")
DRIVE_LISTING = os.path.join(P.AUDIT, "drive-listing.jsonl")

csv.field_size_limit(1 << 30)


def audit_for(root: str) -> str:
    tag = "".join(c if c.isalnum() else "-" for c in root).strip("-").lower()
    return os.path.join(P.AUDIT, "SOURCE-AUDIT-{}.csv".format(tag))


def done_file(root: str) -> str:
    tag = "".join(c if c.isalnum() else "-" for c in root).strip("-").lower()
    return os.path.join(P.AUDIT, "PURGED-{}.csv".format(tag))


def cloud_proven_md5s() -> set:
    """Every md5 Google itself reports holding."""
    out = set()
    if not os.path.exists(DRIVE_LISTING):
        return out
    with io.open(DRIVE_LISTING, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                f = json.loads(line)
            except ValueError:
                continue
            m = (f.get("md5Checksum") or "").lower()
            if m:
                out.add(m)
    return out


def mirrored_md5_by_source() -> dict:
    """Library path -> the md5 computed on the bytes that were uploaded."""
    out = {}
    if not os.path.exists(MIRROR_JOURNAL):
        return out
    for r in csv.DictReader(io.open(MIRROR_JOURNAL, encoding="utf-8",
                                    newline="")):
        if r.get("outcome") in ("written", "already-present") and r.get("md5"):
            out[(r.get("source") or "").lower()] = r["md5"].lower()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-seconds", type=float, default=420.0)
    ap.add_argument("--reason", default="source copy; library holds the content "
                                        "and the cloud copy is proven")
    a = ap.parse_args()

    audit = audit_for(a.root)
    if not os.path.exists(audit):
        print("no audit for {} - run audit_source_tree.py first".format(a.root))
        return 1

    print("loading the cloud proof...")
    drive = cloud_proven_md5s()
    mirrored = mirrored_md5_by_source()
    print("  {:,} md5s in Drive's own listing".format(len(drive)))
    print("  {:,} library files in the mirror journal".format(len(mirrored)))
    if not drive or not mirrored:
        print()
        print("STOPPING: without both the mirror journal and Drive's listing")
        print("  there is no proof the cloud holds anything. Nothing deleted.")
        return 1

    done = set()
    dfile = done_file(a.root)
    if os.path.exists(dfile):
        for r in csv.DictReader(io.open(dfile, encoding="utf-8", newline="")):
            if r.get("Path"):
                done.add(r["Path"].lower())
    if done:
        print("  resuming: {:,} already purged".format(len(done)))

    targets = []
    for r in csv.DictReader(io.open(audit, encoding="utf-8", newline="")):
        if r.get("Verdict") != "HELD":
            continue
        if r["Path"].lower() in done:
            continue
        targets.append((r["Path"], r.get("HeldAt") or "",
                        int(r.get("Bytes") or 0)))

    print("  {:,} HELD file(s) outstanding for {}".format(len(targets), a.root))
    print()

    if not a.apply:
        # Cheap pre-check of proof 3 only, so the report is honest about how
        # many would actually be refused before any hashing happens.
        unproven = sum(1 for _, s, _ in targets
                       if mirrored.get(s.lower(), "") not in drive)
        print("  would delete      : {:,}".format(len(targets) - unproven))
        print("  would REFUSE      : {:,}  (library copy not proven in the cloud)"
              .format(unproven))
        print("  bytes to reclaim  : {:.1f} GB".format(
            sum(b for _, _, b in targets) / (1 << 30)))
        print()
        print("DRY RUN - nothing touched. Re-run with --apply.")
        return 0

    fresh = not os.path.exists(dfile)
    fh = io.open(dfile, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if fresh:
        w.writerow(["Path", "Bytes", "Survivor", "When"])

    t0 = time.time()
    freed = 0
    gone = refused = unproven = 0
    reasons = {}
    try:
        for victim, survivor, size in targets:
            if time.time() - t0 > a.max_seconds:
                break
            md5 = mirrored.get(survivor.lower(), "")
            if not md5 or md5 not in drive:
                unproven += 1
                continue
            try:
                freed += delete_with_surviving_copy(victim, survivor, a.reason)
                gone += 1
                w.writerow([victim, size, survivor,
                            time.strftime("%Y-%m-%dT%H:%M:%S")])
            except DeletionRefused as e:
                refused += 1
                key = str(e).split(":")[0][:60]
                reasons[key] = reasons.get(key, 0) + 1
            if (gone + refused) % 200 == 0 and (gone + refused):
                fh.flush()
                os.fsync(fh.fileno())
                print("  deleted {:,}  refused {:,}  freed {:.1f} GB".format(
                    gone, refused, freed / (1 << 30)), flush=True)
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    print()
    print("this slice: deleted {:,}, freed {:.2f} GB".format(
        gone, freed / (1 << 30)))
    print("  refused by the guard        : {:,}".format(refused))
    for k, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print("      {:>6,}  {}".format(n, k))
    print("  skipped, cloud not proven   : {:,}".format(unproven))
    print()
    print("re-run to continue; every deletion is in {} and the".format(
        os.path.basename(dfile)))
    print("evidence journal that guarded_delete writes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
