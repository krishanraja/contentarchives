r"""Move a named set of files out of the chronology into _Review.

_Review is a holding area, not a bin. Nothing here is deleted: a classifier may
move a file, never destroy one, and the human empties _Review after looking.
That asymmetry is the whole safety model - a wrong move costs a glance, a wrong
delete costs a photograph.

THE SETS, AND THE EVIDENCE FOR EACH

  screenshots  3,022 files. Two independent signals agree - a screenshot
               filename AND either a known screen resolution, an impossible
               aspect ratio, or absent camera EXIF. A camera-original filename
               overrides all of it, which is why messenger-stripped photographs
               are not swept up.

  webgraphics  2,084 PNGs the classifier could not place. Sampled visually:
               a download-arrow icon, a London rail-map tile. PNG plus no other
               signal is a web asset, not a photograph. This is the ONE
               uncertain sub-bucket where a rule is defensible.

  whatsapp     13,368 files received through WhatsApp. 0.5% carry an EXIF date,
               0.6% a camera model, median size 191 KB - the transport strips
               metadata and recompresses. Vision confirmed the bucket is
               genuinely mixed: a toddler in dinosaur pyjamas sits beside a
               forwarded event flyer, metadata-identical. No rule separates
               them, so the whole set goes for human review, EXCEPT the files
               that arrived with camera make/model intact - those were sent
               uncompressed and are real photographs with real provenance.

Manifest follows every move. The journal is fsynced before the manifest is
rewritten, so a crash leaves evidence rather than a mystery.

    python move_to_review.py --set screenshots
    python move_to_review.py --set whatsapp --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

JOURNAL = r"D:\_PhotoAudit\moved-to-review.csv"
SCREENSHOTS = r"D:\_PhotoAudit\SCREENSHOT-CLASSIFICATION.csv"
ORIGIN_MAP = r"D:\_PhotoAudit\ORIGIN-MAP.csv"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def has_camera_exif(path: str) -> bool:
    """Make/Model present in EXIF - the mark of a file that reached us
    uncompressed. WhatsApp strips these, so their survival is meaningful."""
    try:
        with open(lp(path), "rb") as f:
            head = f.read(131072)
    except OSError:
        return False
    if head[:2] != b"\xff\xd8":
        return False
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
                    tag = struct.unpack(en + "H", t[e:e + 2])[0]
                    if tag in (0x010F, 0x0110):
                        return True
            except Exception:
                pass
            break
        i += 2 + ln
    return False


def in_chronology(p: str) -> bool:
    return any(p.lower().startswith(c.lower() + os.sep) for c in P.CHRONOLOGY)


def pick(which: str) -> list[str]:
    if which in ("screenshots", "webgraphics"):
        want = "non-memory" if which == "screenshots" else "uncertain"
        out = []
        for r in csv.DictReader(open(SCREENSHOTS, encoding="utf-8", errors="replace")):
            if r["Verdict"] != want:
                continue
            if which == "webgraphics" and r["Signals"].strip() != "png":
                continue
            p = P.resolve(r["Path"])
            if os.path.exists(lp(p)) and in_chronology(p):
                out.append(p)
        return out

    if which == "whatsapp":
        out, kept = [], 0
        for r in csv.DictReader(open(ORIGIN_MAP, encoding="utf-8", errors="replace")):
            of = (r.get("OriginFolder") or "").lower()
            if "whatsapp im" not in of and "whatsapp vid" not in of:
                continue
            if "sent" in of:
                continue
            p = P.resolve(r.get("LibraryPath", ""))
            if not p or not os.path.exists(lp(p)) or not in_chronology(p):
                continue
            if has_camera_exif(p):
                kept += 1
                continue
            out.append(p)
        print(f"  kept in the chronology (camera make/model intact): {kept:,}")
        return out
    raise SystemExit(f"unknown set: {which}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True,
                    choices=["screenshots", "webgraphics", "whatsapp"])
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    files = sorted(set(pick(a.set)))
    total = 0
    for f in files:
        try:
            total += os.path.getsize(lp(f))
        except OSError:
            pass
    print(f"  {a.set}: {len(files):,} files to move ({total/1024**3:.2f} GB)")

    if not a.apply:
        for f in files[:5]:
            print(f"    {os.path.relpath(f, P.ROOT)}")
        print("\nDRY RUN - nothing moved. Re-run with --apply.")
        return

    os.makedirs(lp(P.REVIEW), exist_ok=True)
    moved: dict[str, str] = {}
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    new_j = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new_j:
            w.writerow(["When", "Set", "From", "To", "Bytes"])
        for src in files:
            rel = os.path.relpath(src, P.ROOT)
            dest = os.path.join(P.REVIEW, rel)
            os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
            stem, ext = os.path.splitext(dest)
            k = 0
            while os.path.exists(lp(dest)):
                k += 1
                dest = f"{stem}__{k}{ext}"
            try:
                sz = os.path.getsize(lp(src))
                shutil.move(lp(src), lp(dest))
            except OSError as e:
                print(f"  FAILED {src}: {e}")
                continue
            moved[src] = dest
            w.writerow([stamp, a.set, src, dest, sz])
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

    print(f"\nmoved {len(moved):,} to _Review; manifest updated. Nothing deleted.")


if __name__ == "__main__":
    main()
