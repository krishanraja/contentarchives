r"""Put back the files _Review should never have held.

A vision pass over the 15,689 files in _Review found 10,004 the model calls real
memories - 9,820 of them photographs. They were swept there by rules of mine
that were wrong: chiefly the judgement that received WhatsApp media is "not
photographs you took". That was true about provenance and false about content.
Most of them are photographs of a life, sent by the people in them.

This restores those files to where they came from.

WHERE "BACK" COMES FROM

The manifest, not a guess. move_to_review.py rewrote each moved file's manifest
row to its _Review path, and moved-to-review.csv journalled From -> To. So the
original location is recorded, not inferred from the folder structure. Where the
journal has no entry - files already in _Review before today - the file stays
put, because inventing a destination is how things end up filed under the wrong
year forever.

WHY THIS IS SAFE TO RUN

Nothing is deleted and nothing is overwritten: a destination that already exists
gets a __1 suffix. If the model was wrong about a file, it returns to the
chronology and can be moved out again - the reverse of the mistake that would
have been permanent.

    python restore_from_review.py
    python restore_from_review.py --apply
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

STORE = r"D:\_enrichment\content_tags.csv"
MOVE_JOURNAL = r"D:\_PhotoAudit\moved-to-review.csv"
THUMBS = r"D:\_thumbs"
JOURNAL = r"D:\_PhotoAudit\restored-from-review.csv"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    # hashes the model called memories
    keep: set[str] = set()
    for r in csv.DictReader(open(STORE, encoding="utf-8", errors="replace")):
        if r["tag"] == "keep" and r["value"] == "yes":
            keep.add(r["hash"])
    print(f"  model says memory : {len(keep):,} hashes")

    # hash -> current path, from the thumbnail cache naming
    # (thumbnails are named by content hash, so the mapping is already built)
    hash_of: dict[str, str] = {}
    for sub in os.listdir(THUMBS):
        d = os.path.join(THUMBS, sub)
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".jpg"):
                    hash_of[fn[:-4]] = ""

    # where each file came from
    came_from: dict[str, str] = {}
    if os.path.exists(MOVE_JOURNAL):
        for r in csv.DictReader(open(MOVE_JOURNAL, encoding="utf-8", errors="replace")):
            if r.get("To") and r.get("From"):
                came_from[os.path.normcase(r["To"])] = r["From"]
    print(f"  journalled moves  : {len(came_from):,}")

    # walk _Review, hash-match against the keep set
    sys.path.insert(0, r"C:\Users\user\dev\contentarchives\engine")
    from store import content_hash                               # noqa: E402

    plan, no_origin, not_keep = [], 0, 0
    scanned = 0
    for dp, dns, fns in os.walk(lp(P.REVIEW)):
        for fn in fns:
            p = os.path.join(dp, fn).replace("\\\\?\\", "")
            scanned += 1
            try:
                h = content_hash(p)
            except OSError:
                continue
            if h not in keep:
                not_keep += 1
                continue
            src = came_from.get(os.path.normcase(p))
            if not src:
                no_origin += 1
                continue
            plan.append((p, src))
            if len(plan) % 2000 == 0:
                print(f"    matched {len(plan):,}...", flush=True)

    print(f"\n  scanned _Review        : {scanned:,}")
    print(f"  to restore             : {len(plan):,}")
    print(f"  stay (not a memory)    : {not_keep:,}")
    print(f"  memory but no recorded origin (left put): {no_origin:,}")

    if not a.apply:
        for s, d in plan[:5]:
            print(f"    {os.path.basename(s)[:40]}  ->  {os.path.relpath(d, P.ROOT)}")
        print("\nDRY RUN - nothing moved. Re-run with --apply.")
        return

    moved: dict[str, str] = {}
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    new_j = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new_j:
            w.writerow(["When", "From", "To", "Why"])
        for src, dest in plan:
            os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
            d = dest
            stem, ext = os.path.splitext(d)
            k = 0
            while os.path.exists(lp(d)):
                k += 1
                d = f"{stem}__{k}{ext}"
            try:
                shutil.move(lp(src), lp(d))
            except OSError as e:
                print(f"  FAILED {os.path.basename(src)}: {e}")
                continue
            moved[src] = d
            w.writerow([stamp, src, d,
                        "vision pass: classified a real memory; restored to the chronology"])
        jf.flush()
        os.fsync(jf.fileno())

    out = []
    with open(P.MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if r and r[0] in moved:
                r[0] = moved[r[0]]
            out.append(r)
    tmp = P.MANIFEST + ".new"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    os.replace(tmp, P.MANIFEST)

    print(f"\nrestored {len(moved):,} files to the chronology; manifest updated")
    dest_top = collections.Counter(
        os.path.relpath(d, P.ROOT).split(os.sep)[1] for d in moved.values()
        if os.path.relpath(d, P.ROOT).count(os.sep) > 1)
    for k, v in dest_top.most_common(6):
        print(f"    {v:>6,}  {k}")


if __name__ == "__main__":
    main()
