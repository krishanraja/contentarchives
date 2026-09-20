r"""Is every media member of an archive already held in the library?

    python verify_archive_members.py --archive "E:\...\takeout-001.zip"
    python verify_archive_members.py --all          # the four Takeout zips on E:

Krish, 2026-09-20, asked for this before the original Takeout archives are
deleted. The audit that cleared 1,094 GB only ever looked at FILES ON DISK.
An archive is a single file to that audit: it was never opened, so nothing in
it was ever compared against the library.

The archives were ingested weeks ago and `arc-progress/*.csv` records that each
member was handled - but "handled" includes `dup` and `skipped`, and a member
skipped as junk then is still a member whose content may exist nowhere else now.
A progress log is a record of a decision, not evidence about content, and this
project's whole history is deletions justified by something that was true
earlier.

So every media member is STREAMED and hashed, and compared against the library's
own blake2b-256. Nothing is extracted to disk: a 891 MB member read whole is what
gets a process killed on this machine, so members go through in chunks and only
the digest is kept.

Read-only. Deletes nothing, and says plainly which members are not held.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import sqlite3
import sys
import zipfile

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402

DB = os.path.join(P.AUDIT, "library.db")
OUT = os.path.join(P.AUDIT, "ARCHIVE-MEMBERS-NOT-HELD.csv")

DEFAULT = [
    r"E:\Laptop 2024 files\takeout-20241122T182033Z-001.zip",
    r"E:\Surface Laptop Backup July 2025\Downloads\takeout-20241122T182033Z-002.zip",
    r"E:\Surface Laptop Backup July 2025\AdFixus\takeout-20241122T182033Z-003.zip",
    r"E:\Surface Laptop Backup July 2025\Downloads\takeout-20241122T182033Z-004.zip",
]

MEDIA = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.bmp', '.tif',
         '.tiff', '.webp', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf',
         '.orf', '.rw2', '.pef', '.srw', '.mp4', '.mov', '.avi', '.m2ts',
         '.3gp', '.mkv', '.wmv', '.m4v', '.mpg', '.mpeg', '.webm', '.mts'}

CHUNK = 8 << 20


def library_hashes() -> set:
    con = sqlite3.connect("file:{}?mode=ro".format(DB.replace("\\", "/")),
                          uri=True)
    try:
        return {h.lower() for (h,) in con.execute(
            "select hash from files where hash is not null and hash != ''")}
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    archives = a.archive or (DEFAULT if a.all else [])
    if not archives:
        print("name an --archive, or --all for the four Takeout zips")
        return 1

    print("loading the library's hashes...")
    lib = library_hashes()
    print("  {:,} distinct content hashes".format(len(lib)))
    print()

    not_held = []
    for arc in archives:
        if not os.path.exists(arc):
            print("  ABSENT: {}".format(arc))
            continue
        held = missing = skipped = 0
        mbytes = 0
        try:
            with zipfile.ZipFile(arc) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    ext = os.path.splitext(info.filename)[1].lower()
                    if ext not in MEDIA:
                        skipped += 1
                        continue
                    h = hashlib.blake2b(digest_size=32)
                    with z.open(info) as fh:
                        while True:
                            b = fh.read(CHUNK)
                            if not b:
                                break
                            h.update(b)
                    if h.hexdigest().lower() in lib:
                        held += 1
                    else:
                        missing += 1
                        mbytes += info.file_size
                        not_held.append([arc, info.filename, info.file_size,
                                         h.hexdigest()])
        except (zipfile.BadZipFile, OSError) as e:
            print("  UNREADABLE {}: {}".format(os.path.basename(arc), e))
            continue

        print("  {}".format(os.path.basename(arc)))
        print("     media members held by the library : {:,}".format(held))
        print("     NOT held                          : {:,}  ({:.2f} GB)".format(
            missing, mbytes / (1 << 30)))
        print("     non-media members skipped         : {:,}".format(skipped))
        print()

    if not_held:
        with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Archive", "Member", "Bytes", "Blake2b256"])
            w.writerows(not_held)
            fh.flush()
            os.fsync(fh.fileno())
        print("{:,} member(s) are NOT in the library: {}".format(
            len(not_held), OUT))
        print("Do not delete these archives until those are dealt with.")
        return 1

    print("Every media member of every archive named is already in the library.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
