r"""Origin map: where every file in the library came from.

The ingest manifest records `destination, source, method` for every file placed
in the library. This turns that into two views:

  ORIGIN-MAP.csv      one row per library file
  ORIGIN-FOLDERS.csv  one row per distinct origin folder

The folder view is the useful one. Quarantining personal material from communal
family content, or separating work output from memories, is a decision about
*where a batch came from* - not about individual files. 59,000 files reduce to
~640 origin folders, and a folder is something a person can actually judge.

    python tools/origin_map.py --library D:\PhotoLibrary --out D:\_PhotoAudit
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from collections import defaultdict

BS = chr(92)


def source_root(src: str) -> str:
    """Coarse bucket for where a file originally lived.

    Ordering matters: a rescued-drive path and a Takeout member can both live
    under D:, so the specific cases are tested before the drive-letter fallback.
    """
    p = src.split("!")[0]
    low = p.lower()
    if "e-drive-rescue" in low:
        return "E: rescued drive"
    if "takeout" in low and p.split("!")[0].lower().endswith((".zip", ".tgz")):
        return "Google Photos (Takeout)"
    if "onedrive" in low:
        return "OneDrive"
    if low.startswith("g:"):
        return "Google Drive (personal)"
    if low.startswith("h:"):
        return "Google Drive (work)"
    if low.startswith("d:"):
        return "D: archive drive"
    if low.startswith("c:"):
        return "C: system drive"
    return "other"


def origin_folder(src: str) -> str:
    """The folder a file came from - deep enough to be worth judging, shallow
    enough to group. Archive members keep `archive.zip!inner/path` form so a
    Takeout export does not collapse into one undifferentiated blob."""
    if "!" in src:
        arc, member = src.split("!", 1)
        parts = member.replace("/", BS).split(BS)
        inner = BS.join(parts[:-1]) if len(parts) > 1 else ""
        return f"{os.path.basename(arc)}!{inner}"
    return os.path.dirname(src)


def build(library: str, manifest: str, out_dir: str) -> tuple[str, str]:
    rows = []
    with open(manifest, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if len(r) >= 3:
                rows.append((r[0], r[1], r[2]))

    folders: dict = defaultdict(lambda: {"n": 0, "bytes": 0, "years": set(),
                                         "root": "", "method": defaultdict(int)})
    out_rows = []
    missing = 0

    for dest, src, method in rows:
        try:
            size = os.path.getsize(dest)
        except OSError:
            size = 0
            missing += 1          # moved or renamed since ingest; still mapped
        root = source_root(src)
        fld = origin_folder(src)
        rel = dest[len(library) + 1:] if dest.startswith(library) else dest
        m = re.search(r"Library" + re.escape(BS) + r"(\d{4})", dest)
        year = m.group(1) if m else ("NoDate" if "NoDate" in dest else "?")

        out_rows.append([rel, src, root, fld, method, size, year])
        e = folders[fld]
        e["n"] += 1
        e["bytes"] += size
        e["years"].add(year)
        e["root"] = root
        e["method"][method] += 1

    files_csv = os.path.join(out_dir, "ORIGIN-MAP.csv")
    folders_csv = os.path.join(out_dir, "ORIGIN-FOLDERS.csv")

    with open(files_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["LibraryPath", "OriginPath", "SourceRoot", "OriginFolder",
                    "Method", "Bytes", "LibraryYear"])
        w.writerows(out_rows)

    frows = []
    for fld, e in sorted(folders.items(), key=lambda kv: -kv[1]["bytes"]):
        yrs = sorted(y for y in e["years"] if y != "?")
        span = f"{yrs[0]}-{yrs[-1]}" if yrs else "?"
        frows.append([fld, e["root"], e["n"], e["bytes"], span,
                      ";".join(f"{k}={v}" for k, v in e["method"].items())])

    with open(folders_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["OriginFolder", "SourceRoot", "Files", "Bytes",
                    "LibraryYearSpan", "Methods"])
        w.writerows(frows)

    print(f"manifest rows: {len(rows):,}")
    print(f"files no longer at their recorded path: {missing:,}")
    print(f"distinct origin folders: {len(folders):,}")
    print(f"written: {files_csv}")
    print(f"written: {folders_csv}")
    return files_csv, folders_csv


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", default=r"D:\PhotoLibrary")
    ap.add_argument("--manifest", default=None,
                    help="default: <library>\\_Catalog\\manifest.csv")
    ap.add_argument("--out", default=r"D:\_PhotoAudit")
    a = ap.parse_args()
    manifest = a.manifest or os.path.join(a.library, "_Catalog", "manifest.csv")
    build(a.library, manifest, a.out)


if __name__ == "__main__":
    main()
