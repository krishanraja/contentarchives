r"""One row per library file, carrying every signal that says what it is.

The goal is an inventory you can actually answer questions from - "where are
the India photos", "what came off the GoPro", "what has no date and no origin"
- rather than a file listing you have to already know the answer to search.

WHERE THE SIGNAL COMES FROM, STRONGEST FIRST

1. THE ORIGIN FOLDER. This is the best identifier in the whole system and it
   costs nothing: a human already named it. `UK December 2015`,
   `Val D'Isere December 2015`, `Bali Big Boyz`, `Munch in NY`, `india\3`.
   No amount of pixel analysis beats someone typing what a folder was. It is
   joined from ORIGIN-MAP.csv, which already traces all 109,208 library files
   back to where they came from.

2. EXIF / container metadata. Date taken, camera make and model, GPS, pixel
   dimensions, duration. The camera's own record of the moment.

3. The filename. Weakest, and it lies (learning 4), so it is recorded as
   evidence and never as a verdict: `Screenshot_20240728-185619_Google.jpg`
   says a great deal, `IMG_0042.JPG` says almost nothing.

WHAT IT DELIBERATELY DOES NOT DO

It does not rename anything. Renaming 90,000 files on the strength of inferred
labels is a large irreversible act built on guesses of varying quality, and the
manifest has to follow every one. The right order is: inventory first, look at
it, then propose renames FROM it as a reviewable list. This tool produces the
evidence; a later pass can propose the edits.

Every derived column is marked with its basis, so a guess is never mistaken for
a reading. `PlaceSource` says whether a place came from GPS or from a folder
someone named years later.

    python build_inventory.py                 # photos only (fast)
    python build_inventory.py --video         # + ffprobe on videos (slow)
    python build_inventory.py --resume
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import struct
import subprocess
import sys

LIB = r"D:\ContentLibrary"

# Every root holding content the inventory claims to describe.
#
# This walked LIB alone, so Archive\ (1,988 files) and ContentProduction\ (18)
# were never inventoried - 33 files, 3.21 GB, appeared "unknown" to a disk
# reconciliation purely because nothing had ever looked at them. Same shape as
# the dedup index that covered 12% of the library: a tool whose reach is
# narrower than its claim, with nothing checking the claim.
#
# An inventory must state what it covers, and the count is the cheap check.
# ONE root. Archive\ and ContentProduction\ now live INSIDE ContentLibrary, so
# listing them separately walks them twice and doubles their rows - measured:
# 3,992 rows for 1,995 files, 36 for 18. The inventory looked bigger and was
# wrong, which is the worse failure of the two.
#
# Roots must be disjoint. If one is ever added, check it is not already inside
# another; the count against disk is the cheap test and it is why this was found.
INVENTORY_ROOTS = [LIB]
ORIGIN_MAP = r"D:\_PhotoAudit\ORIGIN-MAP.csv"
OUT = r"D:\_PhotoAudit\INVENTORY.csv"
CKPT = r"D:\_PhotoAudit\inventory-progress.json"
FFPROBE = (r"C:\Users\user\AppData\Local\Microsoft\WinGet\Packages"
           r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
           r"\ffmpeg-8.1.1-full_build\bin\ffprobe.exe")

PHOTO = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.bmp', '.tif',
         '.tiff', '.webp', '.dng', '.cr2', '.cr3', '.nef', '.arw'}
VIDEO = {'.mp4', '.mov', '.avi', '.m2ts', '.3gp', '.mkv', '.wmv', '.m4v',
         '.mpg', '.mpeg', '.webm', '.mts'}

# Filename shapes that identify a file's nature. Evidence, not verdict.
SHAPES = [
    (re.compile(r"^screenshot[_-]", re.I),                 "screenshot"),
    (re.compile(r"^(gh|gx|gopr|g\d{3})\d+", re.I),         "gopro"),
    (re.compile(r"^whatsapp (image|video)", re.I),         "whatsapp"),
    (re.compile(r"^(img|dsc|dscn|p\d{7})[_-]?\d+", re.I),  "camera"),
    (re.compile(r"^vid[_-]\d{8}", re.I),                   "camera-video"),
    (re.compile(r"^\d{8}[_-]\d{6}"),                       "phone"),
    (re.compile(r"^(received|fb_img|insta)", re.I),        "received"),
    (re.compile(r"^(frame|thumb)[-_]?\d+", re.I),          "extracted-frame"),
]

# Place words that appear in origin folder names. Extend freely; a miss just
# means no PlaceGuess, which is honest.
PLACES = ["india", "bali", "dubai", "ny", "new york", "uk", "london",
          "val d'isere", "vald'isere", "paris", "italy", "spain", "japan",
          "thailand", "sri lanka", "goa", "mumbai", "delhi", "singapore",
          "australia", "sydney", "lisbon", "portugal", "greece", "ibiza",
          "amsterdam", "berlin", "scotland", "wales", "cornwall", "devon"]

MONTHS = ("january february march april may june july august september "
          "october november december").split()


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


# ---------- EXIF ----------
def exif_all(path: str) -> dict:
    """Date, device, GPS and dimensions from a JPEG's EXIF, parsed directly.

    Extends autopilot's exif_ym, which already walks the IFD chain and follows
    the ExifIFD pointer; this additionally follows the GPS IFD and keeps the
    tags that say what took the picture and where.
    """
    out: dict = {}
    try:
        with open(lp(path), "rb") as f:
            head = f.read(196608)
    except OSError:
        return out
    if head[:2] != b"\xff\xd8":
        return out
    i = 2
    while i < len(head) - 4:
        if head[i] != 0xFF:
            i += 1; continue
        mk = head[i + 1]
        if mk in (0xD8, 0x01) or 0xD0 <= mk <= 0xD7:
            i += 2; continue
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
                gps_off = None
                for _ in range(4):
                    n = struct.unpack(en + "H", t[off:off + 2])[0]
                    nxt = None
                    for k in range(n):
                        e = off + 2 + k * 12
                        tag, typ, cnt = struct.unpack(en + "HHI", t[e:e + 8])
                        vo = struct.unpack(en + "I", t[e + 8:e + 12])[0]
                        if tag in (0x9003, 0x0132) and typ == 2 and cnt >= 19:
                            s = t[vo:vo + 19].decode("ascii", "ignore")
                            if re.match(r"\d{4}:\d{2}:\d{2}", s):
                                out.setdefault("DateTaken", s.replace(":", "-", 2))
                        elif tag in (0x010F, 0x0110) and typ == 2:
                            v = t[vo:vo + cnt].split(b"\x00")[0].decode("ascii", "ignore").strip()
                            if v:
                                out["Make" if tag == 0x010F else "Model"] = v
                        elif tag in (0xA002, 0x0100) and cnt == 1:
                            out.setdefault("Width", vo)
                        elif tag in (0xA003, 0x0101) and cnt == 1:
                            out.setdefault("Height", vo)
                        elif tag == 0x8769:
                            nxt = vo
                        elif tag == 0x8825:
                            gps_off = vo
                    if gps_off is not None and "Lat" not in out:
                        try:
                            gn = struct.unpack(en + "H", t[gps_off:gps_off + 2])[0]
                            g: dict = {}
                            for k in range(gn):
                                e = gps_off + 2 + k * 12
                                tag, typ, cnt = struct.unpack(en + "HHI", t[e:e + 8])
                                vo2 = struct.unpack(en + "I", t[e + 8:e + 12])[0]
                                if tag in (0x0001, 0x0003) and typ == 2:
                                    g[tag] = t[e + 8:e + 9].decode("ascii", "ignore")
                                elif tag in (0x0002, 0x0004) and typ == 5 and cnt == 3:
                                    vals = []
                                    for j in range(3):
                                        num, den = struct.unpack(en + "II", t[vo2 + j * 8:vo2 + j * 8 + 8])
                                        vals.append(num / den if den else 0)
                                    g[tag] = vals[0] + vals[1] / 60 + vals[2] / 3600
                            if 0x0002 in g and 0x0004 in g:
                                lat, lon = g[0x0002], g[0x0004]
                                if g.get(0x0001, "N") == "S":
                                    lat = -lat
                                if g.get(0x0003, "E") == "W":
                                    lon = -lon
                                out["Lat"], out["Lon"] = round(lat, 6), round(lon, 6)
                        except Exception:
                            pass
                    if nxt is None:
                        break
                    off = nxt
            except Exception:
                pass
            break
        i += 2 + ln
    return out


def probe_video(path: str) -> dict:
    out: dict = {}
    if not os.path.exists(FFPROBE):
        return out
    try:
        r = subprocess.run([FFPROBE, "-v", "quiet", "-print_format", "json",
                            "-show_format", "-show_streams", path],
                           capture_output=True, timeout=25)
        d = json.loads(r.stdout or b"{}")
    except Exception:
        return out
    tags = {k.lower(): v for k, v in (d.get("format", {}).get("tags") or {}).items()}
    for k in ("creation_time", "com.apple.quicktime.creationdate"):
        if k in tags:
            out.setdefault("DateTaken", str(tags[k])[:19].replace("T", " "))
    for k in ("com.apple.quicktime.model", "model"):
        if k in tags:
            out["Model"] = tags[k]
    for k in ("com.apple.quicktime.make", "make"):
        if k in tags:
            out["Make"] = tags[k]
    loc = tags.get("location") or tags.get("com.apple.quicktime.location.iso6709")
    if loc:
        m = re.match(r"([+-]\d+\.?\d*)([+-]\d+\.?\d*)", str(loc))
        if m:
            out["Lat"], out["Lon"] = float(m.group(1)), float(m.group(2))
    try:
        out["Duration"] = round(float(d["format"]["duration"]), 1)
    except Exception:
        pass
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            out.setdefault("Width", s.get("width"))
            out.setdefault("Height", s.get("height"))
            break
    return out


def event_from_folder(folder: str) -> tuple[str, str]:
    """(EventGuess, PlaceGuess) read out of a folder a human named."""
    if not folder:
        return "", ""
    leaf = folder.replace("/", "\\").rstrip("\\").split("\\")[-1]
    leaf = re.sub(r"^(Photos from \d{4}|DCIM|Camera|Pictures|Downloads)$", "", leaf, flags=re.I)
    low = folder.lower()
    place = next((p for p in PLACES if re.search(rf"(^|[^a-z]){re.escape(p)}([^a-z]|$)", low)), "")
    if leaf and not re.fullmatch(r"[\d\W_]+", leaf):
        return leaf.strip(), place.title()
    return "", place.title()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", action="store_true", help="ffprobe videos too (slow)")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    # The origin map cannot be joined on path alone, for two reasons found the
    # hard way: its LibraryPath column is MIXED - some absolute (D:\ContentLibrary\Archive\..),
    # some relative to D:\ContentLibrary (NoDate\x.jpg) - and it predates
    # apply_split.py, so its `Library\..` paths are now `Personal\..`. Joining
    # on the exact string matched nothing at all and silently produced an
    # inventory with no origin column, which looked like "no data" rather than
    # like a bug.
    #
    # So: normalise, then fall back to basename. The fallback is recorded in
    # OriginJoin rather than hidden, because a basename match is weaker
    # evidence than a path match and the sheet should say so.
    print("loading the origin map...")
    origin: dict[str, tuple[str, str, str]] = {}
    by_base: dict[str, tuple[str, str, str]] = {}
    ambiguous: set[str] = set()
    if os.path.exists(ORIGIN_MAP):
        with open(ORIGIN_MAP, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                raw = (r.get("LibraryPath") or "").strip()
                if not raw:
                    continue
                full = raw if re.match(r"^[A-Za-z]:\\", raw) else os.path.join(LIB, raw)
                val = (r.get("OriginFolder", ""), r.get("SourceRoot", ""),
                       r.get("OriginPath", ""))
                origin[os.path.normcase(full)] = val
                b = os.path.basename(full).lower()
                if b in by_base and by_base[b] != val:
                    ambiguous.add(b)
                else:
                    by_base[b] = val
    for b in ambiguous:
        by_base.pop(b, None)
    print(f"  {len(origin):,} origin rows, {len(by_base):,} unambiguous basenames "
          f"({len(ambiguous):,} names dropped as ambiguous)")

    # A --limit run is a TEST. It must never be able to truncate the real
    # artefact. This exact mistake destroyed a 79,300-row inventory twice in
    # one day: `--limit 40` opened OUT with "w" and wrote 40 rows over it, and
    # the second time the damaged file was then snapshotted to H:, propagating
    # the loss to the backup.
    out_path = OUT if not a.limit else OUT.replace(".csv", f".sample{a.limit}.csv")
    if a.limit:
        print(f"  --limit run: writing to {out_path} (the real inventory is untouched)")

    rows = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["LibraryPath", "Side", "Year", "Month", "Ext", "Kind", "Bytes",
                    "DateTaken", "DateSource", "Make", "Model", "Width", "Height",
                    "Duration", "Lat", "Lon", "PlaceGuess", "PlaceSource",
                    "EventGuess", "FilenameShape", "OriginFolder", "SourceRoot",
                    "OriginJoin"])
        for root in INVENTORY_ROOTS:
          if not os.path.isdir(root): continue
          for dp, dns, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(lp(p))
                except OSError:
                    continue
                ext = os.path.splitext(fn)[1].lower()
                kind = "photo" if ext in PHOTO else "video" if ext in VIDEO else "other"
                # Side is relative to the root being walked. Using LIB for
                # every root would render an Archive\ file's side as "..".
                rel = os.path.relpath(p, root).split(os.sep)
                side = rel[0] if root == LIB else os.path.basename(root)
                ym = re.search(r"(\d{4})[\\/](\d{4})-(\d{2})", p)
                year, month = (ym.group(1), ym.group(3)) if ym else ("", "")

                meta: dict = {}
                if kind == "photo" and ext in (".jpg", ".jpeg"):
                    meta = exif_all(p)
                elif kind == "video" and a.video:
                    meta = probe_video(p)
                dsrc = "exif" if kind == "photo" and meta.get("DateTaken") else \
                       "container" if kind == "video" and meta.get("DateTaken") else \
                       "folder" if year else ""

                key = os.path.normcase(p)
                if key in origin:
                    of, sr, _op = origin[key]; ojoin = "exact"
                elif fn.lower() in by_base:
                    of, sr, _op = by_base[fn.lower()]; ojoin = "basename"
                else:
                    of, sr, _op, ojoin = "", "", "", "none"
                ev, place = event_from_folder(of)
                psrc = ""
                if meta.get("Lat") is not None:
                    psrc = "gps"
                elif place:
                    psrc = "origin-folder"

                shape = next((n for rx, n in SHAPES if rx.match(fn)), "")
                w.writerow([p, side, year, month, ext, kind, st.st_size,
                            meta.get("DateTaken", ""), dsrc,
                            meta.get("Make", ""), meta.get("Model", ""),
                            meta.get("Width", ""), meta.get("Height", ""),
                            meta.get("Duration", ""),
                            meta.get("Lat", ""), meta.get("Lon", ""),
                            place, psrc, ev, shape, of, sr, ojoin])
                rows += 1
                if rows % 5000 == 0:
                    print(f"  {rows:,} files", flush=True)
                if a.limit and rows >= a.limit:
                    print(f"\nstopped at --limit {a.limit}")
                    print(f"inventory: {out_path}")
                    return
    print(f"\n{rows:,} rows -> {OUT}")


if __name__ == "__main__":
    main()
