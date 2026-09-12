r"""Regenerate the thumbnails that were built sideways, and name what changed.

    python refix_rotated.py            # count them, write nothing
    python refix_rotated.py --apply

WHY

engine/thumbnail.py did not honour EXIF orientation, and `convert("RGB")`
discards EXIF - so a phone photo held portrait became a landscape thumbnail with
no orientation tag left to recover from. That sideways thumbnail is what the
classifier read and what the face detector is about to read. Measured on rotated
files: 11 faces found sideways against 13 upright, a 15% loss, before counting
whatever a rotated image does to "what is this a picture of".

Fixed in thumbnail.py on 2026-09-12. This repairs the thumbnails already made.

THE ORIGINALS ARE NOT TOUCHED, AND THAT IS DELIBERATE

EXIF orientation is data, not damage. Every modern viewer honours it, the
photographs were never sideways, and re-encoding tens of thousands of JPEGs to
fix a display convention is a lossy, irreversible bulk edit of the very files
this project exists to protect. Our thumbnails were wrong. The library was not.

WHAT IT WRITES

ROTATED-REDO.txt, one content hash per line: the files whose thumbnail changed
and whose classification was therefore made from a sideways image. Feed it to
classify_live.py --only-list to re-judge exactly those and nothing else.
"""

from __future__ import annotations

import argparse
import csv
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
sys.path.insert(0, r"D:\_PhotoAudit\scripts")

import paths as P                                                # noqa: E402

AUDIT = P.AUDIT
THUMBS = r"D:\_thumbs"
OUT = os.path.join(AUDIT, "ROTATED-REDO.txt")
SIDEWAYS = {3, 6, 8}                       # 180, 90 CW, 90 CCW
JPEG = (".jpg", ".jpeg")


def orientation(path: str):
    """The EXIF orientation tag, read from the header bytes alone.

    Opening each file with PIL to read one integer costs minutes across 57,000
    images. This reads the first 64 KB and walks the APP1 segment.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return None
    if head[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(head) - 4:
        if head[i] != 0xFF:
            i += 1
            continue
        mk = head[i + 1]
        if mk in (0xD8, 0x01) or 0xD0 <= mk <= 0xD7:
            i += 2
            continue
        if mk == 0xDA:
            break
        try:
            ln = struct.unpack(">H", head[i + 2:i + 4])[0]
        except struct.error:
            break
        seg = head[i + 4:i + 2 + ln]
        if mk == 0xE1 and seg[:6] == b"Exif\x00\x00":
            t = seg[6:]
            try:
                en = "<" if t[:2] == b"II" else ">"
                off = struct.unpack(en + "I", t[4:8])[0]
                n = struct.unpack(en + "H", t[off:off + 2])[0]
                for k in range(n):
                    e = off + 2 + k * 12
                    tag, _, _ = struct.unpack(en + "HHI", t[e:e + 8])
                    if tag == 0x0112:
                        return struct.unpack(en + "H", t[e + 8:e + 10])[0]
            except Exception:                                    # noqa: BLE001
                return None
            break
        i += 2 + ln
    return None


def hash_index() -> dict:
    idx = {}
    for src in ("MIGRATION-HASHES.csv", "HASH-INDEX.csv"):
        p = os.path.join(AUDIT, src)
        if not os.path.exists(p):
            continue
        with open(p, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.reader(f):
                if len(r) >= 3 and r[1].isdigit():
                    idx[r[0].lower()] = r[2]
    return idx


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    idx = hash_index()
    roots = [P.PERSONAL, P.COMMUNAL, P.NODATE, P.PENDING]
    found, redone, nohash, failed = 0, 0, 0, 0
    hashes = []

    make = None
    if a.apply:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "th", os.path.join(HERE, "..", "engine", "thumbnail.py"))
        th = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(th)
        make = th.make

    for root in roots:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if not fn.lower().endswith(JPEG):
                    continue
                p = os.path.join(dp, fn)
                if orientation(p) not in SIDEWAYS:
                    continue
                found += 1
                h = idx.get(p.lower())
                if not h:
                    nohash += 1
                    continue
                hashes.append(h)
                if not a.apply:
                    continue
                # Remove the sideways one first: make() may skip an existing
                # file, and a silent skip here would leave the whole point
                # of this script undone while reporting success.
                dst = os.path.join(THUMBS, h[:2], h + ".jpg")
                try:
                    if os.path.exists(dst):
                        os.remove(dst)
                except OSError:
                    pass
                if make(p, THUMBS, 512):
                    redone += 1
                else:
                    failed += 1
                if redone and redone % 500 == 0:
                    print("  {:,} regenerated".format(redone), flush=True)

    print("sideways originals found : {:,}".format(found))
    print("  without a known hash   : {:,}".format(nohash))
    if a.apply:
        print("  thumbnails regenerated : {:,}".format(redone))
        print("  failed                 : {:,}".format(failed))
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(set(hashes))))
        print("wrote {} ({:,} hashes to re-judge, ~${:.2f})".format(
            OUT, len(set(hashes)), len(set(hashes)) * 0.453 / 1000))
    else:
        print("  would re-judge         : {:,} files, ~${:.2f}".format(
            len(set(hashes)), len(set(hashes)) * 0.453 / 1000))
        print("\ncount only. --apply to regenerate.")


if __name__ == "__main__":
    main()
