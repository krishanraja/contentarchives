r"""Ingest media from any folder tree into the library, deduped and dated.

Generalises what the Takeout and second-machine ingests did, so a newly discovered
source - an extracted WhatsApp backup, an old phone dump, a digitised tape folder -
can be brought in without writing another one-off script.

Two properties that matter:

**Same volume means free.** A source on the library's own volume is hardlinked in,
not copied. The library gains a name for bytes already on disk; the source folder
can then be deleted and the library keeps the content. That is how 293 GB entered
this library at zero cost.

**Duplicates are decided on content.** Size first because it costs no I/O and rules
out almost everything, then a whole-file hash. A filename never decides anything.

    python ingest_tree.py --source "D:\GoogleCloud\..." --label whatsapp
    python ingest_tree.py --source ... --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopilot as ap                                          # noqa: E402

# Extensions this will ingest. A format missing from here is not rejected -
# it is INVISIBLE, which is worse: the walk never sees it and reports success.
# `.mod` was absent, and .MOD is what JVC and Panasonic camcorders write, so a
# 93.7 MB family video sat in a folder called Movies and no ingest ever looked
# at it. Camcorder and raw formats are included now for the same reason.
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp",
             ".tif", ".tiff", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf",
             ".orf", ".rw2", ".pef", ".srw",
             ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".3g2", ".webm",
             ".wmv", ".mpg", ".mpeg", ".mpe",
             ".mod", ".tod", ".mts", ".m2ts", ".vob", ".flv", ".asf", ".mxf"}
AUDIT = r"D:\_PhotoAudit"

# Below this a "photo" is an emoji, sticker or thumbnail, not a memory. They are
# reported, never silently dropped.
MIN_MEDIA = 20 * 1024


def same_volume(a: str, b: str) -> bool:
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == \
           os.path.splitdrive(os.path.abspath(b))[0].lower()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--label", default="tree")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--divert", action="append", default=[], metavar="FOLDER",
                   help="folder name whose files go to the divert root instead of "
                        "the library - stickers, reaction GIFs and similar. They "
                        "are kept, not discarded: deleting the source afterwards "
                        "would otherwise lose them.")
    p.add_argument("--divert-root", default=r"D:\_Staging\diverted")
    p.add_argument("--min-size", type=int, default=MIN_MEDIA,
                   help="skip media smaller than this many bytes. The default is a "
                        "guess about stickers and thumbnails, and a guess is not a "
                        "reason to lose a photo - check what it excludes "
                        "(check_tiny.py) before relying on it.")
    a = p.parse_args()

    src_root = os.path.abspath(a.source)
    report = os.path.join(AUDIT, f"INGEST-{a.label}.csv")

    if not os.path.isdir(ap.lp(src_root)):
        sys.exit(f"no such folder: {src_root}")
    lib_root = os.path.dirname(ap.LIB)
    if src_root.lower().startswith(lib_root.lower()):
        sys.exit(f"refusing: source is inside the library ({src_root})")

    print(f"source : {src_root}")
    print(f"library: {ap.LIB}")
    link = same_volume(src_root, ap.LIB)
    print(f"method : {'hardlink - costs no additional bytes' if link else 'copy'}")

    files = []
    for dp, _, fns in os.walk(ap.lp(src_root)):
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in MEDIA_EXT:
                full = os.path.join(dp, fn).replace("\\\\?\\", "")
                try:
                    files.append((os.path.getsize(ap.lp(full)), full))
                except OSError:
                    pass
    print(f"media  : {len(files):,} files, "
          f"{sum(s for s, _ in files)/1024**3:.2f} GB")

    tiny = [f for f in files if f[0] < a.min_size]
    files = [f for f in files if f[0] >= a.min_size]
    print(f"         {len(tiny):,} under {a.min_size//1024} KB skipped as "
          f"stickers/thumbnails ({sum(s for s, _ in tiny)/1024**2:.1f} MB)")

    print("indexing the library...")
    by_size, ns = ap.build_index()
    ap.load_hash_cache()

    rows, stats = [], defaultdict(int)
    added_bytes = 0
    for i, (size, src) in enumerate(sorted(files, reverse=True), 1):
        if i % 500 == 0:
            print(f"  {i:,}/{len(files):,}  new={stats['new']} dup={stats['dup']}",
                  flush=True)
        name = os.path.basename(src)

        dup_of = None
        cands = by_size.get(size, ())
        if cands:
            try:
                h = ap.full_hash(src, size)
            except OSError as e:
                rows.append(["failed", src, "", str(e)])
                stats["failed"] += 1
                continue
            for c in cands:
                try:
                    if ap.full_hash(c) == h:
                        dup_of = c
                        break
                except OSError:
                    continue
        if dup_of:
            rows.append(["duplicate", src, dup_of, "whole-file hash match"])
            stats["dup"] += 1
            continue

        if not a.apply:
            rows.append(["new", src, "(dry run)", ""])
            stats["new"] += 1
            added_bytes += size
            continue

        divert_as = next((d for d in a.divert
                          if f"\\{d.lower()}\\" in src.lower() + "\\"), None)
        if divert_as:
            dest_dir = os.path.join(a.divert_root, divert_as)
            y = "diverted"
        else:
            y, m = ap.ym_for(src, name, os.path.dirname(src), {})
            dest_dir = os.path.join(ap.LIB, y, f"{y}-{m}") if y else ap.NODATE
        os.makedirs(ap.lp(dest_dir), exist_ok=True)
        dest = os.path.join(dest_dir, name)
        stem, ext = os.path.splitext(dest)
        n = 0
        while os.path.exists(ap.lp(dest)):
            n += 1
            dest = f"{stem}__{n}{ext}"
        try:
            if link:
                os.link(ap.lp(src), ap.lp(dest))
            else:
                shutil.copyfile(ap.lp(src), ap.lp(dest))
            if os.path.getsize(ap.lp(dest)) != size:
                raise OSError("size mismatch after placement")
        except OSError as e:
            rows.append(["failed", src, "", str(e)])
            stats["failed"] += 1
            continue

        by_size.setdefault(size, []).append(dest)
        ns.add((name.lower(), size))
        ap.record(dest, src, "link" if link else "copy")
        rows.append(["new", src, dest, y or "NoDate"])
        stats["new"] += 1
        added_bytes += size

    ap.flush_hash_cache()

    with open(report, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Outcome", "Source", "Destination", "Note"])
        w.writerows(rows)
        for size, t in tiny:
            w.writerow(["skipped-tiny", t, "", f"{size} bytes"])

    print()
    print("DRY RUN - nothing written." if not a.apply else "APPLIED")
    print("-" * 68)
    for k in ("new", "dup", "failed"):
        print(f"  {k:>10}: {stats[k]:>7,}")
    print(f"  {'new bytes':>10}: {added_bytes/1024**3:.2f} GB"
          f"{'  (hardlinked - 0 bytes added to disk)' if link else ''}")

    years = defaultdict(int)
    for r in rows:
        if r[0] == "new" and a.apply:
            years[r[3]] += 1
    if years:
        print()
        print("  new files by year:")
        for y in sorted(years):
            print(f"    {y}: {years[y]:,}")
    print()
    print(f"report: {report}")


if __name__ == "__main__":
    main()
