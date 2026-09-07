r"""Which parts of a Takeout export actually carry files the library lacks?

Reads only a zip's CENTRAL DIRECTORY - member names and sizes - so a 50 GB
archive is triaged in seconds without extracting or hashing a single byte.

This exists because export partitioning is not stable. The Sep-5 and Sep-7
exports of the same photo set placed 1,595 of part 001's files in different
parts. So "I already ingested 001, skip it" is unsound across exports: parts
can only be judged by what they contain, never by their number.

    python zip_fingerprint.py "C:\...\takeout-...-001.zip"
    python zip_fingerprint.py *.zip

A (name, size) match is the same fast pre-check autopilot's ingest uses. It is
TRIAGE, not proof: the hash dedup at ingest remains the authority. A part
reported as fully held is safe to deprioritise, not to assume identical.
"""

from __future__ import annotations

import os
import sys
import zipfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopilot as ap                                          # noqa: E402


CACHE = r"D:\_PhotoAudit\arc-sizes.json"


def persist_ground_truth(path: str, sizes: dict) -> None:
    """Record this archive's member list so the part stays VERIFIABLE after the
    archive is deleted.

    Reading a central directory and not saving it is a trap: the ingest deletes
    each archive once it believes every member landed, and at that moment the
    only surviving record of what the archive contained is this file. Without it
    "did everything arrive?" becomes unanswerable, and a deletion justified by an
    unanswerable question is how files get lost.
    """
    import json
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        cache = {}
    key = f"{os.path.basename(path)}|{os.stat(path).st_size}"
    if key not in cache:
        cache[key] = sizes
        try:
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))
            print(f"  ground truth saved ({len(sizes):,} members) - survives deletion")
        except Exception as e:
            print(f"  WARNING: could not save ground truth: {e}")


def fingerprint(path: str, ns: set) -> None:
    name = os.path.basename(path)
    print(f"\n{'='*70}\n{name}\n{'='*70}")
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        print(f"  UNREADABLE: {e}")
        return

    sizes: dict[str, int] = {}
    media = held = 0
    unheld_bytes = held_bytes = 0
    unheld_by_folder: Counter = Counter()
    nonmedia = 0

    for i in z.infolist():
        if i.is_dir():
            continue
        base = os.path.basename(i.filename)
        if os.path.splitext(base)[1].lower() not in ap.MEDIA:
            nonmedia += 1
            continue
        media += 1
        sizes[i.filename] = i.file_size
        if (base.lower(), i.file_size) in ns:
            held += 1
            held_bytes += i.file_size
        else:
            unheld_bytes += i.file_size
            parts = i.filename.split("/")
            unheld_by_folder[parts[2] if len(parts) > 2 else "(root)"] += 1
    z.close()
    persist_ground_truth(path, sizes)

    unheld = media - held
    print(f"  media members      : {media:,}   (+{nonmedia:,} json/sidecar ignored)")
    print(f"  already in library : {held:,}  ({held_bytes/1024**3:.1f} GB)")
    print(f"  NOT in library     : {unheld:,}  ({unheld_bytes/1024**3:.1f} GB)")
    if media:
        print(f"  -> {unheld*100.0/media:.1f}% of this part is new to the library")
    if unheld:
        print("  new files by source folder (top 12):")
        for k, v in unheld_by_folder.most_common(12):
            print(f"      {v:6,}  {k}")
    else:
        print("  -> nothing new: this part is fully represented in the library")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    print("indexing the library (cached)...")
    _by_size, ns = ap.build_index()
    print(f"library index: {len(ns):,} (name,size) pairs")
    for p in args:
        if os.path.exists(p):
            fingerprint(p, ns)
        else:
            print(f"\nmissing: {p}")


if __name__ == "__main__":
    main()
