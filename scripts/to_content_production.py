r"""Move produced content out of the personal library and into ContentProduction.

The library is meant to hold memories. A TV interview and a set of long 4K
recordings are work output - the user grouped them together explicitly - and
keeping them in `Library/YYYY/YYYY-MM` makes the eventual personal/communal split
noisier for no benefit.

Moves are within one volume, so they are renames: instant, and they do not touch
the bytes. Hardlinked files keep their other name, so nothing is orphaned.

The manifest is rewritten to follow each file. That matters more than it sounds:
the origin map is derived from the manifest, and a manifest that still points at
`Library\2026\...` for a file that now lives in `ContentProduction` is exactly the
kind of quiet drift the whole tracking discipline exists to prevent.

    python to_content_production.py            # show what would move
    python to_content_production.py --apply
"""

from __future__ import annotations

import csv
import datetime
import os
import shutil
import sys

AUDIT = r"D:\_PhotoAudit"
MANIFEST = r"D:\ContentLibrary\_Catalog\manifest.csv"
JOURNAL = os.path.join(AUDIT, "content-production-moves.csv")

# path -> destination subfolder. Explicit, because these were chosen by a person.
MOVES = {
    r"D:\ContentLibrary\Media\Pending-Segmentation\2026\2026-02\20260205_165928.mp4": "2026",
    r"D:\ContentLibrary\Media\Pending-Segmentation\2026\2026-02\20260205_161023.mp4": "2026",
    r"D:\ContentLibrary\Media\Pending-Segmentation\2026\2026-03\20260305_132059.mp4": "2026",
    r"D:\ContentLibrary\Media\Pending-Segmentation\2026\2026-03\20260305_133914.mp4": "2026",
    r"D:\ContentLibrary\Media\NoDate\EMPLOYER-A_Full -.mp4": "interviews",
}
ROOT = r"D:\ContentLibrary\ContentProduction"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def main() -> None:
    apply = "--apply" in sys.argv
    planned = []

    for src, sub in MOVES.items():
        if not os.path.exists(lp(src)):
            print(f"  MISSING (already moved?)  {src}")
            continue
        size = os.path.getsize(lp(src))
        dest_dir = os.path.join(ROOT, sub)
        dest = os.path.join(dest_dir, os.path.basename(src))
        if os.path.exists(lp(dest)):
            print(f"  SKIP (destination exists)  {dest}")
            continue
        planned.append((src, dest, size))
        print(f"  {size/1024**3:>6.2f} GB  {os.path.basename(src)}  ->  {sub}\\")

    total = sum(s for _, _, s in planned)
    print()
    print(f"{len(planned)} files, {total/1024**3:.2f} GB")

    if not apply:
        print("\nDry run - nothing moved. Re-run with --apply.")
        return
    if not planned:
        return

    moved = []
    for src, dest, size in planned:
        os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
        shutil.move(lp(src), lp(dest))
        if os.path.getsize(lp(dest)) != size:
            raise SystemExit(f"size changed moving {src} - stopping")
        moved.append((src, dest, size))
        print(f"  moved  {os.path.basename(dest)}")

    # --- follow the files in the manifest ------------------------------------
    remap = {s: d for s, d, _ in moved}
    rows = []
    with open(MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if r and r[0] in remap:
                r[0] = remap[r[0]]
            rows.append(r)
    tmp = MANIFEST + ".new"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, MANIFEST)
    print(f"\nmanifest updated: {len(remap)} paths followed to ContentProduction")

    new = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["From", "To", "Bytes", "Reason", "When"])
        when = datetime.datetime.now().isoformat(timespec="seconds")
        for src, dest, size in moved:
            w.writerow([src, dest, size,
                        "user-classified: produced content, not personal memory", when])
    print(f"journal: {JOURNAL}")
    print("\nRe-run origin_map.py and track.py so the canon reflects this.")


if __name__ == "__main__":
    main()
