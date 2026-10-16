r"""Refresh the backup drive from the cloud and from H:. Nothing waits on it.

    python stages/13_app/backup_to_drive.py                  # report what it would copy
    python stages/13_app/backup_to_drive.py --apply          # copy, every file checked
    python stages/13_app/backup_to_drive.py --apply --max-gb 50 --drive F:\

WHY (Krish, 2026-10-16)

"I expect all this to be done automatically in the future we just use the app.
The external D (currently F) Drive should just be a backup, nothing should rely
on this external drive, everything should be able to be done on H drive." So
the cloud is the record, H: (Google Drive, My Drive\ContentLibrary) holds the
photographs, and this drive only receives copies. This script is the one thing
that refreshes it, and nothing in the app or the record needs it to have run.

WHAT IT DOES

  1. FINDS THE DRIVE BY WHAT IS ON IT, not by its letter: the first of D: to Z:
     holding _PhotoAudit\library.db and _enrichment\answers.csv. None plugged
     in is not a failure: it says so and exits 0.
  2. THE RECORD: the newest night of the cloud's export (export_record.py:
     every answer, the journal, and the catalogue of every photograph) is
     written to <drive>\_cloud-record\<day>\*.csv.gz and checked against its
     sha256. A day already there is never overwritten, and none is deleted.
  3. THE PHOTOGRAPHS: every photograph in the catalogue whose md5 this drive
     does not already hold is copied from H:\My Drive\ContentLibrary\<path> to
     <drive>\ContentLibrary\<path>. It is hashed as it is read and must match
     Drive's own md5, written under a temporary name and renamed only when it
     does. A file already at the destination is never overwritten, nothing is
     ever deleted, and every copy is journalled in
     <drive>\_PhotoAudit\backup-from-h.csv. A run stops at --max-gb (50 by
     default; the next run carries on) and at the first file that does not
     match, because a wrong byte read through the mount means something is
     wrong with the mount, not with one photograph.

"Already holds" means the md5 is in the mirror journal (h-mirror.csv: the
library copied to H: from this drive) or in this script's own journal. A
photograph that reached H: straight from a phone is in neither, which is
exactly what this copies.

Reading through H: downloads each file into Drive for desktop's cache, which
evicts as it needs to; --max-gb also bounds how much one run pulls.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import os
import string
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401

H_LIBRARY = r"H:\My Drive\ContentLibrary"
MARKERS = (os.path.join("_PhotoAudit", "library.db"), os.path.join("_enrichment", "answers.csv"))
MIRROR_OK = ("written", "already-present")        # seed_index.MIRROR_OK
NAMES = ("answers", "journal", "catalogue")
JOURNAL_COLS = ["when", "rel_path", "md5", "bytes", "outcome"]


class Mismatch(Exception):
    """Bytes read from H: did not match Drive's md5."""


def is_backup(root: str) -> bool:
    return all(os.path.exists(os.path.join(root, m)) for m in MARKERS)


def find_drive(roots=None):
    """The first root holding every marker, or None. Default: D:\\ to Z:\\."""
    if roots is None:
        roots = ["{}:\\".format(c) for c in string.ascii_uppercase[3:]]
    for r in roots:
        if is_backup(r):
            return r
    return None


def journal_path(drive: str) -> str:
    return os.path.join(drive, "_PhotoAudit", "backup-from-h.csv")


def held_md5s(drive: str) -> set:
    """md5s this drive already holds: mirrored from it, or copied onto it."""
    held = set()
    mirror = os.path.join(drive, "_PhotoAudit", "h-mirror.csv")
    if os.path.exists(mirror):
        with io.open(mirror, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("md5") and (r.get("outcome") or "").strip().lower() in MIRROR_OK:
                    held.add(r["md5"].strip().lower())
    j = journal_path(drive)
    if os.path.exists(j):
        with io.open(j, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("md5") and r.get("outcome") in ("copied", "already-there"):
                    held.add(r["md5"].strip().lower())
    return held


def fetch_record(cloud):
    """(day, {name: (rows, sha256, gzip bytes)}) for the newest night, or (None, {})."""
    newest = cloud.select("record_exports", "select=day&order=day.desc&limit=1")
    if not newest:
        return None, {}
    day = newest[0]["day"]
    out = {}
    for r in cloud.select("record_exports", "select=name,rows,sha256,body&day=eq.{}".format(day)):
        b = r["body"]
        out[r["name"]] = (int(r["rows"]), r["sha256"], bytes.fromhex(b[2:]) if b.startswith("\\x") else b)
    return day, out


def save_record(drive: str, day: str, rec: dict, apply: bool) -> list:
    """Write a night's copies under <drive>\\_cloud-record\\<day>. -> problems.

    Each body is checked against its sha256 before it is written and again
    after; a file already there is never overwritten - the same bytes are
    skipped, different bytes are a problem to look at.
    """
    problems = []
    dest = os.path.join(drive, "_cloud-record", str(day))
    for name in NAMES:
        if name not in rec:
            problems.append("{}: not in the cloud's export for {}".format(name, day))
            continue
        rows, sha, body = rec[name]
        if hashlib.sha256(body).hexdigest() != sha:
            problems.append("{}: the cloud's copy does not match its sha256".format(name))
            continue
        path = os.path.join(dest, name + ".csv.gz")
        if os.path.exists(path):
            with open(path, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() != sha:
                    problems.append("{}: a different copy for {} is already there, left alone".format(name, day))
            continue
        if not apply:
            continue
        os.makedirs(dest, exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)                 # a fresh name: nothing is overwritten
        with open(path, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != sha:
                problems.append("{}: did not read back from the drive".format(name))
    return problems


def catalogue_rows(rec: dict) -> list:
    rows, _, body = rec["catalogue"]
    return list(csv.DictReader(io.StringIO(gzip.decompress(body).decode("utf-8"))))


def local(root: str, rel_path: str) -> str:
    return os.path.join(root, *rel_path.split("/"))


def copy_one(src: str, dst: str, md5: str) -> int:
    """Copy src to dst, hashing as it reads. -> bytes. Raises Mismatch, never overwrites."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    h, n = hashlib.md5(), 0
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            for b in iter(lambda: fi.read(8 << 20), b""):
                h.update(b)
                fo.write(b)
                n += len(b)
            fo.flush()
            os.fsync(fo.fileno())
        if h.hexdigest() != md5:
            raise Mismatch(src)
        if os.path.exists(dst):               # appeared meanwhile: leave it alone
            os.remove(tmp)
            return 0
        os.rename(tmp, dst)
        return n
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def copy_photos(rows, held: set, h_root: str, drive: str, max_bytes: int, apply: bool) -> dict:
    """Bring this drive every catalogued photograph it lacks. -> counts.

    counts["mismatch"] is the rel_path that stopped the run, or "".
    """
    c = {"wanted": 0, "copied": 0, "bytes": 0, "already-there": 0, "missing-on-h": 0,
         "budget": 0, "mismatch": ""}
    todo = sorted((r for r in rows if r.get("md5") and r.get("rel_path")
                   and r["md5"].lower() not in held), key=lambda r: r["rel_path"])
    c["wanted"] = len(todo)
    new_journal = not os.path.exists(journal_path(drive))
    jf = None
    if apply:
        os.makedirs(os.path.dirname(journal_path(drive)), exist_ok=True)
        jf = io.open(journal_path(drive), "a", encoding="utf-8", newline="")
        jw = csv.writer(jf)
        if new_journal:
            jw.writerow(JOURNAL_COLS)
    try:
        for r in todo:
            rel, md5 = r["rel_path"], r["md5"].lower()
            src, dst = local(h_root, rel), local(os.path.join(drive, "ContentLibrary"), rel)
            when = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            if os.path.exists(dst):
                c["already-there"] += 1
                if apply:
                    jw.writerow([when, rel, md5, "", "already-there"])
                continue
            if not os.path.exists(src):
                c["missing-on-h"] += 1
                continue
            if c["bytes"] >= max_bytes:
                c["budget"] = 1
                break
            if not apply:
                c["copied"] += 1
                c["bytes"] += os.path.getsize(src)
                continue
            try:
                n = copy_one(src, dst, md5)
            except Mismatch:
                jw.writerow([when, rel, md5, "", "mismatch"])
                c["mismatch"] = rel
                break
            jw.writerow([when, rel, md5, n, "copied"])
            jf.flush()
            c["copied"] += 1
            c["bytes"] += n
    finally:
        if jf:
            jf.close()
    return c


def main(argv=None, cloud=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", default="", help="the backup drive's root; found by its markers if omitted")
    ap.add_argument("--h-root", default=H_LIBRARY)
    ap.add_argument("--max-gb", type=float, default=50.0)
    ap.add_argument("--skip-photos", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    drive = a.drive or find_drive()
    if not drive or not is_backup(drive):
        print("backup drive not connected - nothing to refresh (nothing waits on it)")
        return 0
    print("backup drive: {}".format(drive))

    if cloud is None:
        from cloud import Cloud
        cloud = Cloud()
    day, rec = fetch_record(cloud)
    if not day:
        print("the cloud has no export yet (export_record.py runs nightly) - nothing to copy")
        return 0
    print("cloud record: {} ({})".format(day, ", ".join(
        "{} {:,}".format(n, rec[n][0]) for n in NAMES if n in rec)))
    problems = save_record(drive, day, rec, a.apply)
    for p in problems:
        print("   PROBLEM: " + p)
    if problems:
        return 1
    print("record {} {}".format("saved under" if a.apply else "would be saved under",
                                os.path.join(drive, "_cloud-record", str(day))))

    if a.skip_photos:
        return 0
    if not os.path.isdir(a.h_root):
        print("H: is not mounted ({}) - photographs skipped this time".format(a.h_root))
        return 0
    c = copy_photos(catalogue_rows(rec), held_md5s(drive), a.h_root, drive,
                    int(a.max_gb * (1 << 30)), a.apply)
    print("photographs this drive lacks: {:,}   {} {:,} ({:.2f} GB)   already there {:,}   "
          "missing on H: {:,}".format(c["wanted"], "copied" if a.apply else "would copy",
                                      c["copied"], c["bytes"] / (1 << 30), c["already-there"],
                                      c["missing-on-h"]))
    if c["budget"]:
        print("stopped at --max-gb {:g}; the next run carries on".format(a.max_gb))
    if c["mismatch"]:
        print("STOPPING: bytes read from H: did not match Drive's md5 for {} - "
              "nothing was written for it; check the mount before the next run".format(c["mismatch"]))
        return 1
    if not a.apply:
        print("dry run - nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
