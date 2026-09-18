r"""Drop ledger rows for files a HUMAN deliberately removed - by name, never by absence.

    python drop_removed_rows.py --list removed.txt            # report only
    python drop_removed_rows.py --list removed.txt --apply
    python drop_removed_rows.py --list removed.txt --apply --block

WHY THIS IS NOT reconcile_disk.py

`reconcile_disk.py` exists to say the opposite of this: the disk is the truth,
the inventory is a claim about it, and its output is ALWAYS ADDITIVE - "unknown
files are candidates for inclusion, never for removal". That rule was paid for
twice (a 12%-coverage index that admitted 21,649 duplicates, and an inventory
overwritten by a careless write), and it must not be relaxed. An unmounted
drive, a typo'd root, a permissions blip: every one of them makes thousands of
files look absent, and a tool that drops rows for absent paths would quietly
destroy the record of a 200,000-file process the first time one happened.

So absence is NEVER the reason here. The reason is a NAMED LIST, and absence is
only a precondition: a listed path that still exists on disk stops the whole
run, because it means the list and the disk disagree about what happened and
this tool cannot tell which of them is stale.

WHY IT IS NEEDED

Three records are keyed on PATH - INVENTORY.csv (LibraryPath), HASH-INDEX.csv
(LibraryPath) and MIGRATION-HASHES.csv (headerless, path in column 0) - and
`build_db.load_files()` reads them rather than walking the disk. A deletion
therefore stales all three, and nothing notices.

On 2026-09-18 Krish removed seven files from the Intimate folder himself. Every
run of the H: mirror since then has retried all seven, logged
"copy failed: [Errno 2] No such file or directory", and - because the mirror's
denominator is INVENTORY.csv - could never reach zero remaining. The chain is
written to FAIL while files remain so the scheduled task restarts, so those
seven rows alone would have kept it restarting forever while reporting a
partial upload. A stale row is not a cosmetic problem.

THE BLOCKLIST

`--block` appends each dropped file's hash to PURGED-HASHES.csv, the
no-reingest list. For content removed on purpose this is the point: the phones
and albums still to be ingested hold other copies, and dropping the row without
blocking the hash means the next ingest puts it straight back. The hash is read
from the records BEFORE they are rewritten, because afterwards there is nowhere
left to read it from.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_shared"))

AUDIT = r"D:\_PhotoAudit"
JOURNAL = os.path.join(AUDIT, "ledger-row-drops.csv")
BLOCKLIST = os.path.join(AUDIT, "PURGED-HASHES.csv")

# (file, the column holding the path, has a header row)
RECORDS = [
    ("INVENTORY.csv", "LibraryPath", True),
    ("HASH-INDEX.csv", "LibraryPath", True),
    ("MIGRATION-HASHES.csv", 0, False),
]

csv.field_size_limit(1 << 30)


def norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p.strip().strip('"')))


def read_list(path: str) -> list[str]:
    out = []
    for line in io.open(path, encoding="utf-8-sig"):
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def hashes_for(targets: set[str]) -> dict[str, str]:
    """path -> hash, from whichever record carries one. Read BEFORE the rewrite."""
    found: dict[str, str] = {}
    for name, col, header in RECORDS:
        path = os.path.join(AUDIT, name)
        if not os.path.exists(path):
            continue
        fh = io.open(path, encoding="utf-8", newline="")
        if header:
            for r in csv.DictReader(fh):
                p = norm(r.get(col) or "")
                if p in targets:
                    for k in ("Hash", "hash", "blake2b", "Blake2b"):
                        if r.get(k):
                            found.setdefault(p, r[k])
                            break
        else:
            for row in csv.reader(fh):
                if len(row) > 1 and norm(row[0]) in targets:
                    found.setdefault(norm(row[0]), row[1])
        fh.close()
    return found


def rewrite(path: str, col, header: bool, targets: set[str], apply: bool) -> int:
    """Return how many rows match. Writes atomically, and only with --apply."""
    if not os.path.exists(path):
        return 0
    tmp = path + ".dropping"
    dropped = 0
    fi = io.open(path, encoding="utf-8", newline="")
    fo = io.open(tmp, "w", encoding="utf-8", newline="") if apply else None
    try:
        if header:
            rd = csv.DictReader(fi)
            wr = csv.DictWriter(fo, fieldnames=rd.fieldnames) if apply else None
            if apply:
                wr.writeheader()
            for r in rd:
                if norm(r.get(col) or "") in targets:
                    dropped += 1
                    continue
                if apply:
                    wr.writerow(r)
        else:
            wr = csv.writer(fo) if apply else None
            for row in csv.reader(fi):
                if row and norm(row[col]) in targets:
                    dropped += 1
                    continue
                if apply:
                    wr.writerow(row)
    finally:
        fi.close()
        if fo:
            fo.flush()
            os.fsync(fo.fileno())
            fo.close()
    if apply:
        if dropped:
            # A .bak beside it, not an overwrite in place: the record of a
            # 200,000-file process was destroyed once by a careless write.
            bak = path + ".bak-rowdrop"
            if os.path.exists(bak):
                os.remove(bak)
            os.replace(path, bak)
            os.replace(tmp, path)
        else:
            os.remove(tmp)
    return dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True,
                    help="file of paths, one per line, that a human removed")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--block", action="store_true",
                    help="append each dropped hash to PURGED-HASHES.csv")
    ap.add_argument("--reason", default="removed by the user on purpose")
    a = ap.parse_args()

    listed = read_list(a.list)
    if not listed:
        print("the list is empty - nothing named, nothing dropped")
        return 1
    targets = {norm(p) for p in listed}

    # PRECONDITION: a listed file that still exists means the list is wrong
    # about what happened, and this tool cannot tell which side is stale.
    still_here = [p for p in listed if os.path.exists(p)]
    if still_here:
        print("STOPPED: {} listed path(s) still exist on disk.".format(len(still_here)))
        for p in still_here[:20]:
            print("  " + p)
        print("  Nothing was changed. Either the file was not removed, or the")
        print("  list names the wrong path. Both need a human, not a rewrite.")
        return 2

    print("{} path(s) named, all absent from disk".format(len(listed)))
    known = hashes_for(targets)
    print("{} of them carry a hash in the records".format(len(known)))
    print()

    counts = {}
    for name, col, header in RECORDS:
        n = rewrite(os.path.join(AUDIT, name), col, header, targets, a.apply)
        counts[name] = n
        print("  {:<22} {:>4} row(s) {}".format(
            name, n, "dropped" if a.apply else "would be dropped"))

    total = sum(counts.values())
    if not a.apply:
        print()
        print("dry run. --apply to rewrite, --block to add the hashes to the")
        print("no-reingest list so the next phone ingest does not restore them.")
        return 0

    now = dt.datetime.now().isoformat(timespec="seconds")
    new = not os.path.exists(JOURNAL)
    with io.open(JOURNAL, "a", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        if new:
            wr.writerow(["when", "path", "hash", "reason", "records"])
        for p in listed:
            wr.writerow([now, p, known.get(norm(p), ""), a.reason,
                         ";".join("{}={}".format(k, v) for k, v in counts.items())])
        fh.flush()
        os.fsync(fh.fileno())
    print()
    print("journalled {} row(s) to {}".format(len(listed), JOURNAL))

    if a.block:
        have = set()
        if os.path.exists(BLOCKLIST):
            for row in csv.reader(io.open(BLOCKLIST, encoding="utf-8", newline="")):
                if row:
                    have.add(row[0].strip().lower())
        added = 0
        with io.open(BLOCKLIST, "a", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh)
            for p in listed:
                h = known.get(norm(p), "")
                if h and h.lower() not in have:
                    wr.writerow([h, os.path.basename(p), a.reason, now])
                    have.add(h.lower())
                    added += 1
            fh.flush()
            os.fsync(fh.fileno())
        print("blocked {} new hash(es) in {}".format(added, BLOCKLIST))
        missing = [p for p in listed if not known.get(norm(p))]
        if missing:
            print("NOT blocked - no hash on record for {} file(s):".format(len(missing)))
            for p in missing:
                print("  " + os.path.basename(p))

    print()
    print("{} row(s) dropped across {} record(s).".format(total, len(RECORDS)))
    print("library.db is now stale for these paths: run")
    print("  python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
