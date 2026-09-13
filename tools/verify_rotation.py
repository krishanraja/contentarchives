r"""Check that thumbnails of rotated photographs really are the right way up.

    python verify_rotation.py --sample 6      # 0 correct, 1 wrong, 2 can't tell

WHY

engine/thumbnail.py never honoured EXIF orientation and convert("RGB") discards
EXIF, so a portrait photograph became a landscape thumbnail with no orientation
tag left to recover from. That is what the classifier read for 79,000 files and
what face detection was about to read: measured 11 faces found sideways against
13 upright, a 15% loss, before counting what a rotated image does to "what is
this a picture of".

refix_rotated.py regenerates those thumbnails, and its progress output counts
how many it REWROTE - which proves it wrote files, not that it turned them. A
run that rewrote 19,870 thumbnails and left every one sideways would print
exactly the same numbers.

So this compares orientation directly: for an original whose EXIF says portrait,
the thumbnail must be taller than it is wide.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SIDEWAYS = {5, 6, 7, 8}          # EXIF orientations that swap the axes


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redo", default=r"D:\_PhotoAudit\ROTATED-REDO.txt")
    ap.add_argument("--inventory", default=r"D:\_PhotoAudit\INVENTORY.csv")
    ap.add_argument("--thumbs", default=r"D:\_thumbs")
    ap.add_argument("--sample", type=int, default=6)
    a = ap.parse_args()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rf", os.path.join(HERE, "refix_rotated.py"))
    rf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rf)
    from PIL import Image

    # hash -> a library path, so a hash from ROTATED-REDO can be re-examined
    paths = {}
    if os.path.exists(a.inventory):
        idx = {}
        try:
            import master_sheet as MS
            idx = MS.load_hash_index()
        except Exception:                                        # noqa: BLE001
            pass
        for p, (_sz, h) in idx.items():
            paths.setdefault(h, p)

    hashes = []
    if os.path.exists(a.redo):
        hashes = [ln.strip() for ln in io.open(a.redo, encoding="utf-8") if ln.strip()]
    if len(hashes) < 3:
        print("verify: ROTATED-REDO.txt not written yet, nothing to check")
        return 2

    random.shuffle(hashes)
    checked = bad = 0
    for h in hashes:
        if checked >= a.sample:
            break
        src = paths.get(h)
        thumb = os.path.join(a.thumbs, h[:2], h + ".jpg")
        if not src or not os.path.exists(src) or not os.path.exists(thumb):
            continue
        try:
            o = rf.orientation(src)
            if o not in SIDEWAYS:
                continue                 # not one of the rotated ones
            with Image.open(src) as im:
                sw, sh = im.size
            with Image.open(thumb) as im:
                tw, th = im.size
        except Exception:                                        # noqa: BLE001
            continue
        checked += 1
        # EXIF says the axes are swapped, so the upright thumbnail must be the
        # OPPOSITE orientation to the raw pixels of the original.
        want_portrait = sw > sh
        got_portrait = th > tw
        if want_portrait != got_portrait:
            bad += 1
            print("  {}  original {}x{} exif {} -> thumbnail {}x{} is still sideways"
                  .format(h[:12], sw, sh, o, tw, th))
    if checked == 0:
        print("verify: could not examine any rotated pair yet")
        return 2
    print("verify: checked {} rotated thumbnails, {} still sideways".format(
        checked, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
