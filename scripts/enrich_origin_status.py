r"""Add origin status to the inventory: does the original still exist, and would
deleting it actually free anything?

This is preparation for removing originals from the disparate places they were
collected from. That is a destructive downstream act, so the column has to say
more than "yes it is still there".

THE DISTINCTION THAT MATTERS

43,173 library files entered by HARDLINK - same volume, so the library gained a
name for bytes already on disk. The "original" and the library entry are ONE
FILE. Deleting the original removes a name and frees ZERO bytes.

66,034 entered by COPY. Those are genuinely two sets of bytes, and deleting the
original frees real space.

A plain exists/not-exists flag would conflate them, and a folder listing already
made exactly that mistake once here: it showed 264 GB across six backup folders
that were 94-97% hardlinked, where deleting everything would have freed 1-3 GB
per folder. Learning 28.

COLUMNS ADDED

  OriginPath          where it came from
  OriginMethod        link | copy
  OriginStatus        present | gone | archive-consumed | volume-offline
  OriginFreeableBytes bytes actually recovered by deleting it - 0 for hardlinks
  OriginSameInode     for present originals: proof, not inference

`archive-consumed` is its own status because 43,101 files came from inside
Takeout archives that were deleted after their contents were verified. There is
no original to remove and nothing was lost - recording that as "gone" would read
like an absence to investigate.

    python enrich_origin_status.py
"""

from __future__ import annotations

import csv
import os
import string

INVENTORY = r"D:\_PhotoAudit\INVENTORY.csv"
ORIGIN_MAP = r"D:\_PhotoAudit\ORIGIN-MAP.csv"
OUT = r"D:\_PhotoAudit\INVENTORY-ENRICHED.csv"

NEW_COLS = ["OriginPath", "OriginMethod", "OriginStatus",
            "OriginFreeableBytes", "OriginSameInode"]


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def online_volumes() -> set[str]:
    """Which drive letters are actually mounted right now.

    An origin on an unmounted volume is NOT gone. Reporting it as missing would
    invite deleting a library file believing its source had vanished, or worse,
    conclude the original is already removed and stop looking for it.
    """
    return {d + ":" for d in string.ascii_uppercase if os.path.exists(d + ":\\")}


def main() -> None:
    online = online_volumes()
    print(f"volumes online: {' '.join(sorted(online))}")

    origin: dict[str, tuple[str, str]] = {}
    with open(ORIGIN_MAP, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            lp_ = (r.get("LibraryPath") or "").strip()
            if not lp_:
                continue
            key = os.path.normcase(lp_ if lp_[1:2] == ":" else
                                   os.path.join(r"D:\ContentLibrary", lp_))
            origin[key] = (r.get("OriginPath", ""), r.get("Method", ""))
    print(f"origin map: {len(origin):,} entries")

    rows = list(csv.DictReader(open(INVENTORY, encoding="utf-8", errors="replace")))
    fields = list(rows[0].keys()) if rows else []
    for c in NEW_COLS:
        if c not in fields:
            fields.append(c)

    tally: dict[str, int] = {}
    freeable = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            libp = r.get("LibraryPath", "")
            op, method = origin.get(os.path.normcase(libp), ("", ""))
            status, free, same_inode = "", "", ""

            if not op:
                status = "unrecorded"
            elif "!" in op:
                status = "archive-consumed"
            else:
                vol = op[:2].upper()
                if vol not in online:
                    status = "volume-offline"
                elif not os.path.exists(lp(op)):
                    status = "gone"
                else:
                    status = "present"
                    try:
                        a, b = os.stat(lp(op)), os.stat(lp(libp))
                        same = (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)
                        same_inode = "yes" if same else "no"
                        # a hardlink frees nothing; only a separate copy does
                        free = 0 if same else a.st_size
                        freeable += free or 0
                    except OSError:
                        same_inode = "unreadable"

            r["OriginPath"] = op
            r["OriginMethod"] = method
            r["OriginStatus"] = status
            r["OriginFreeableBytes"] = free
            r["OriginSameInode"] = same_inode
            tally[status] = tally.get(status, 0) + 1
            w.writerow(r)

    print(f"\n{len(rows):,} inventory rows enriched -> {OUT}\n")
    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {v:>8,}  {k}")
    print(f"\n  deleting every PRESENT original would free "
          f"{freeable/1024**3:.1f} GB of real bytes")
    print("  (hardlinked originals are counted as 0 - they are the same file)")


if __name__ == "__main__":
    main()
