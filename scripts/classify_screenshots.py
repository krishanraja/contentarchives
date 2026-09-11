r"""Find the images in the chronology that are not memories, and move them to _Review.

Screenshots are the largest contaminant of a personal photo library. They carry real
timestamps, so they file themselves perfectly into month folders, and there are
usually far more of them than photographs.

Signals, read from file headers only - no decoding, no third-party libraries:

  filename        Screenshot_20240312-101533_Chrome.jpg, Screen Shot 2019-...,
                  image.png, unnamed.png
  exact screen    a screenshot matches the device resolution exactly. A photograph
  dimensions      essentially never does
  no camera EXIF  cameras and phones always write Make/Model. Screenshots do not
  PNG from a      phone cameras produce JPEG or HEIC. A PNG is a screenshot or a
  phone           download
  extreme ratio   banners and web graphics are far from any camera aspect ratio

The rule from ORGANISING.md, and the reason this can run unattended:

    A classifier may move a file. It may never delete one.

Three buckets, and only one of them moves:

  confident memory     camera EXIF present, or a camera-original filename -> stays
  confident non-memory two or more signals agree                          -> _Review
  uncertain            anything else                                      -> STAYS

Uncertain deliberately stays in the chronology. A false positive costs a moment of
noise while browsing; a false negative costs a memory. Those are not symmetric.

    python classify_screenshots.py            # report
    python classify_screenshots.py --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import shutil
import struct
import sys
from collections import Counter

LIBROOT = r"D:\ContentLibrary"
CHRONOLOGY = ["Personal", "Communal", "Library", "NoDate"]
REVIEW = os.path.join(LIBROOT, "_Review")
MANIFEST = os.path.join(LIBROOT, "_Catalog", "manifest.csv")
JOURNAL = r"D:\_PhotoAudit\screenshot-review.csv"
REPORT = r"D:\_PhotoAudit\SCREENSHOT-CLASSIFICATION.csv"

IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".gif"}

SCREENSHOT_NAME = re.compile(
    r"^(screenshot|screen[ _-]?shot|screencapture|capture[_ -]\d|"
    r"image\.|unnamed|download(\s*\(\d+\))?\.|photo_\d+_)", re.I)
CAMERA_NAME = re.compile(
    r"^(IMG[_-]|IMAG\d|MVI_|DSC|DSCN|PXL_|VID[_-]|GOPR|GX\d|GH\d|DJI[_-]"
    r"|\d{8}[_-]\d{6}|\d{4}-\d{2}-\d{2}[ _]\d{2}\.\d{2}\.\d{2}"
    r"|PANO|BURST|P\d{7}|WP_\d{8}|SAM_\d|CIMG\d|PICT\d|100_\d)", re.I)

# Screen resolutions that a camera could never produce, because their aspect
# ratio is not one cameras use. These are real evidence.
#
# The first version of this set also contained 1024x768, 768x1024, 1536x2048 and
# 2048x1536 - iPad resolutions. They are equally standard *camera* resolutions,
# and including them flagged 3,152 genuine photographs as screenshots, among them
# a run of IMAG#### files straight off a Windows Phone camera. A 4:3 frame proves
# nothing either way; only the tall phone-screen ratios do.
SCREENS = {
    (1080, 1920), (1080, 2160), (1080, 2220), (1080, 2280), (1080, 2340),
    (1080, 2400), (1080, 2408), (1440, 2560), (1440, 2960), (1440, 3040),
    (1440, 3088), (1440, 3120), (1440, 3200), (1125, 2436), (1170, 2532),
    (1179, 2556), (1242, 2688), (1284, 2778), (1290, 2796), (750, 1334),
    (828, 1792), (640, 1136), (720, 1280), (1668, 2388), (2048, 2732),
    (1366, 768), (1440, 900), (1680, 1050), (1280, 800), (2880, 1800),
    (3024, 1964), (2560, 1600), (1512, 982), (1470, 956), (3456, 2234),
}
SCREENS |= {(h, w) for w, h in SCREENS}

# Resolutions cameras and screens share. Never evidence on their own.
AMBIGUOUS = {(1024, 768), (768, 1024), (1536, 2048), (2048, 1536),
             (1920, 1080), (1080, 1920), (2560, 1440), (1440, 2560),
             (3840, 2160), (2160, 3840), (1280, 720), (720, 1280),
             (1600, 1200), (1200, 1600), (2592, 1944), (1944, 2592)}
SCREENS -= AMBIGUOUS


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def read_header(path: str, n: int = 65536) -> bytes:
    try:
        with open(lp(path), "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def jpeg_info(b: bytes):
    """(width, height, has_camera_exif) from a JPEG header."""
    if not b.startswith(b"\xff\xd8"):
        return None
    w = h = 0
    has_cam = False
    i = 2
    while i < len(b) - 4:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > len(b):
            break
        seglen = struct.unpack(">H", b[i + 2:i + 4])[0]
        seg = b[i + 4:i + 2 + seglen]
        if marker == 0xE1 and seg[:6] == b"Exif\x00\x00":
            # Make (0x010F) and Model (0x0110) present means a real camera
            has_cam = b"\x0f\x01" in seg[:4000] or b"\x10\x01" in seg[:4000]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if len(seg) >= 5:
                h, w = struct.unpack(">HH", seg[1:5])
            break
        i += 2 + seglen
    return w, h, has_cam


def png_info(b: bytes):
    if not b.startswith(b"\x89PNG\r\n\x1a\n") or len(b) < 24:
        return None
    w, h = struct.unpack(">II", b[16:24])
    return w, h, False


def classify(path: str):
    """Returns (verdict, signals)."""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    signals = []

    if SCREENSHOT_NAME.match(name):
        signals.append("filename")

    b = read_header(path)
    info = jpeg_info(b) if ext in (".jpg", ".jpeg") else (
        png_info(b) if ext == ".png" else None)

    w = h = 0
    has_cam = False
    if info:
        w, h, has_cam = info
        if (w, h) in SCREENS:
            signals.append(f"screen {w}x{h}")
        if w and h:
            ratio = max(w, h) / min(w, h)
            if ratio > 3.2:
                signals.append(f"ratio {ratio:.1f}")
        if ext in (".jpg", ".jpeg") and not has_cam:
            signals.append("no camera exif")
    if ext == ".png":
        signals.append("png")

    # A camera-original filename outranks everything, including a screen-size
    # match. It used not to, and that alone flagged thousands of real photos:
    # messenger platforms strip EXIF, so a forwarded photograph has no camera
    # tags, and if its resolution also collided with a screen size the filename
    # was overruled. The device that wrote IMAG0647.jpg was a camera.
    if CAMERA_NAME.match(name):
        return "memory", ["camera filename"]
    if has_cam:
        return "memory", ["camera exif"]

    strong = [s for s in signals if s.startswith(("filename", "screen", "ratio"))]
    if signals and (len(strong) >= 1 and len(signals) >= 2):
        return "non-memory", signals
    return "uncertain", signals


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    files = []
    for sub in CHRONOLOGY:
        root = os.path.join(LIBROOT, sub)
        if not os.path.isdir(lp(root)):
            continue
        for dp, _, fns in os.walk(lp(root)):
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in IMG_EXT:
                    files.append(os.path.join(dp, fn).replace("\\\\?\\", ""))
    print(f"{len(files):,} images in the chronology")

    rows, verdicts = [], Counter()
    for i, p in enumerate(files, 1):
        if i % 5000 == 0:
            print(f"  {i:,}/{len(files):,} classified", flush=True)
        v, sig = classify(p)
        verdicts[v] += 1
        rows.append([v, p, ";".join(sig)])

    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Verdict", "Path", "Signals"])
        w.writerows(rows)

    print()
    for v in ("memory", "uncertain", "non-memory"):
        print(f"  {verdicts[v]:>7,}  {v}")
    print()
    print("SAMPLE OF WHAT WOULD MOVE")
    print("-" * 74)
    for v, p, sig in [r for r in rows if r[0] == "non-memory"][:20]:
        print(f"  {os.path.basename(p)[:44]:<44} {sig[:26]}")

    if not a.apply:
        print(f"\n{verdicts['non-memory']:,} files would move to _Review")
        print(f"report: {REPORT}")
        print("\nReport only. Re-run with --apply.")
        return

    moved = {}
    new = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new:
            w.writerow(["From", "To", "Signals", "When"])
        when = dt.datetime.now().isoformat(timespec="seconds")
        for v, p, sig in rows:
            if v != "non-memory":
                continue
            rel = os.path.relpath(p, LIBROOT)
            dest = os.path.join(REVIEW, rel)
            os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
            d = dest
            stem, ext = os.path.splitext(d)
            k = 0
            while os.path.exists(lp(d)):
                k += 1
                d = f"{stem}__{k}{ext}"
            w.writerow([p, d, sig, when])
            try:
                shutil.move(lp(p), lp(d))
                moved[p] = d
            except OSError as e:
                print(f"  FAILED {p}: {e}")
        jf.flush()
        os.fsync(jf.fileno())

    out = []
    with open(MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if r and r[0] in moved:
                r[0] = moved[r[0]]
            out.append(r)
    tmp = MANIFEST + ".new"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    os.replace(tmp, MANIFEST)

    print(f"\nmoved {len(moved):,} files to {REVIEW}; manifest updated")
    print(f"journal: {JOURNAL}")
    print("\nNothing was deleted. Review the tree and delete what you agree with.")


if __name__ == "__main__":
    main()
