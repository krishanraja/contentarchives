r"""Sort the freeable bytes on D: into tiers by how much judgement each needs.

"Free 200 GB" is only answerable once the freeable pile is separated by risk. The
audit found 226.7 GB outside the library, but that pile contains 53,228 jpgs and
2,303 mp4s that are NOT in the library - and a family funeral video sits among
them. Treating that as bulk to delete is how the earlier loss happened.

Tiers, most obviously safe first:

  1 regenerable   games, installers, ISOs - a download re-creates them exactly
  2 redundant     byte-identical copies of each other, keeping one
  3 documents     work archives, mail, decks, music - the owner's call, not mine
  4 MEDIA         photos and video not in the library - REVIEW, DO NOT DELETE

Read-only. Produces lists; deletes nothing.
"""

from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict

SRC = r"D:\_PhotoAudit\SPACE-FREEABLE.csv"
OUT = r"D:\_PhotoAudit\SPACE-TIERS.csv"
MEDIA_OUT = r"D:\_PhotoAudit\MEDIA-NOT-IN-LIBRARY.csv"

REGENERABLE_DIRS = [r"D:\SteamLibrary"]
REGENERABLE_EXT = {".iso", ".exe", ".msi", ".pak", ".fmf", ".apk", ".vpk", ".bin"}
DOC_EXT = {".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".pdf", ".pst",
           ".ost", ".mp3", ".m4a", ".aiff", ".wav", ".aax", ".txt", ".csv",
           ".zip", ".rar", ".7z", ".crypt14", ".crypt15", ".eml", ".msg"}
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp",
             ".tif", ".tiff", ".dng", ".cr2", ".nef", ".arw", ".mp4", ".mov",
             ".avi", ".mkv", ".m4v", ".3gp", ".webm", ".wmv", ".mpg", ".mpeg"}

# Media this size or smaller is almost certainly an asset, icon or thumbnail
# rather than a photograph. Kept as a separate line, never merged into "safe".
ASSET_MAX = 120 * 1024


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def tier(path: str, ext: str, size: int) -> str:
    low = path.lower()
    if any(low.startswith(d.lower() + "\\") for d in REGENERABLE_DIRS):
        return "1-regenerable"
    if ext in REGENERABLE_EXT:
        return "1-regenerable"
    if ext in MEDIA_EXT:
        return "4-media-small" if size <= ASSET_MAX else "4-MEDIA"
    if ext in DOC_EXT:
        return "3-documents"
    return "3-documents"


def main() -> None:
    rows = []
    with open(SRC, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["Bytes"]), r["Path"], r["Ext"].lower()))
    print(f"{len(rows):,} freeable files, {sum(s for s, _, _ in rows)/1024**3:.1f} GB")

    tiered = defaultdict(list)
    for size, path, ext in rows:
        tiered[tier(path, ext, size)].append((size, path, ext))

    # --- tier 2: byte-identical copies within the freeable set --------------
    # Only files big enough to matter, and only where size collides at all.
    by_size = defaultdict(list)
    for size, path, ext in rows:
        if size >= 8 * 1024 * 1024:
            by_size[size].append(path)
    candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}
    print(f"hashing {sum(len(p) for p in candidates.values()):,} size-colliding "
          f"files >=8 MB to find true copies...")

    redundant = []
    for size, paths in candidates.items():
        digests = defaultdict(list)
        for p in paths:
            try:
                h = hashlib.blake2b(digest_size=16)
                with open(lp(p), "rb") as fh:
                    for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
                        h.update(chunk)
                digests[h.hexdigest()].append(p)
            except OSError:
                continue
        for d, ps in digests.items():
            if len(ps) > 1:
                keep = sorted(ps, key=len)[0]
                for extra in ps:
                    if extra != keep:
                        redundant.append((size, extra, keep))

    redundant_paths = {p for _, p, _ in redundant}
    redundant_bytes = sum(s for s, _, _ in redundant)

    print()
    print("TIERS")
    print("=" * 90)
    order = ["1-regenerable", "2-redundant", "3-documents", "4-media-small", "4-MEDIA"]
    labels = {
        "1-regenerable": "regenerable - games, installers, ISOs. Re-download recreates them",
        "2-redundant": "byte-identical copies of another freeable file (one kept)",
        "3-documents": "documents, mail archives, decks, music - your call",
        "4-media-small": "media under 120 KB - icons, thumbnails, web assets",
        "4-MEDIA": "PHOTOS AND VIDEO NOT IN THE LIBRARY - review, do not delete",
    }
    totals = {}
    for t in order:
        if t == "2-redundant":
            b, n = redundant_bytes, len(redundant)
        else:
            items = [x for x in tiered[t] if x[1] not in redundant_paths]
            b, n = sum(s for s, _, _ in items), len(items)
        totals[t] = b
        print(f"  {b/1024**3:>7.1f} GB  {n:>7,}  {labels[t]}")
    print("  " + "-" * 86)
    safe = totals["1-regenerable"] + totals["2-redundant"]
    print(f"  {safe/1024**3:>7.1f} GB           no-judgement total (tiers 1+2)")
    print(f"  {(safe + totals['3-documents'] + totals['4-media-small'])/1024**3:>7.1f} GB"
          f"           including documents and sub-120KB assets")

    # --- write it all out ---------------------------------------------------
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Tier", "Bytes", "Path", "Ext", "DuplicateOf"])
        for t in order:
            if t == "2-redundant":
                for size, extra, keep in sorted(redundant, reverse=True):
                    w.writerow([t, size, extra, os.path.splitext(extra)[1].lower(), keep])
            else:
                for size, path, ext in sorted(tiered[t], reverse=True):
                    if path not in redundant_paths:
                        w.writerow([t, size, path, ext, ""])

    media = sorted((x for x in tiered["4-MEDIA"]), reverse=True)
    with open(MEDIA_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Bytes", "Path", "Ext"])
        for size, path, ext in media:
            w.writerow([size, path, ext])

    print()
    print("LARGEST MEDIA NOT IN THE LIBRARY  (these need a decision, not a delete)")
    print("=" * 90)
    for size, path, ext in media[:25]:
        print(f"  {size/1024**2:>8.1f} MB  {path[:78]}")

    folders = defaultdict(lambda: [0, 0])
    for size, path, ext in media:
        d = os.path.dirname(path)
        folders[d][0] += 1
        folders[d][1] += size
    print()
    print("MEDIA-NOT-IN-LIBRARY BY FOLDER")
    print("=" * 90)
    for d, (n, b) in sorted(folders.items(), key=lambda kv: -kv[1][1])[:25]:
        print(f"  {n:>6,} {b/1024**2:>9.1f} MB  {d[:70]}")

    print()
    print(f"written: {OUT}")
    print(f"written: {MEDIA_OUT}  ({len(media):,} files)")


if __name__ == "__main__":
    main()
