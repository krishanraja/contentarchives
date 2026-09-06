r"""Verify every manifest row still points at a file, and explain the ones that don't.

The manifest is the provenance record the origin map is built from. A row pointing
at nothing means either a file was moved without the manifest following it, or the
file is gone.

Only one of those is a problem, so this cross-references the deletion journals and
separates them. A dangling row that matches a journalled, user-directed deletion is
history working correctly. A dangling row nobody can account for is the thing worth
looking at, and it should never appear silently in a count.

    python tools/check_manifest.py
    python tools/check_manifest.py --quiet    # exit code only: 1 if unexplained
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path(r"D:\PhotoLibrary\_Catalog\manifest.csv")
DEFAULT_AUDIT = Path(r"D:\_PhotoAudit")

# Journals that record a deliberate removal, and the column holding the path.
JOURNALS = [
    ("user-directed-deletions.csv", "Path"),
    ("content-production-moves.csv", "From"),
]

# Journals recording removal of the ORIGINAL, not the library entry. A library
# file whose source was classified and removed here is very likely part of the
# same cleanup, but the removal was never recorded at the library end - so it is
# reported as a weaker class of evidence, not as fully accounted for.
SOURCE_JOURNALS = [
    ("FULL-loss-audit.csv", "Path", "Reason"),
    ("to-delete.csv", "Path", "Reason"),
]


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def journalled(audit: Path) -> dict[str, str]:
    """path -> the reason it is no longer where the manifest says."""
    out: dict[str, str] = {}
    for name, col in JOURNALS:
        p = audit / name
        if not p.exists():
            continue
        with open(p, newline="", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                path = row.get(col)
                if path:
                    out[path] = row.get("Reason") or f"recorded in {name}"
    return out


def source_journalled(audit: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, col, reason_col in SOURCE_JOURNALS:
        p = audit / name
        if not p.exists():
            continue
        with open(p, newline="", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                path = row.get(col)
                if path:
                    out[path] = row.get(reason_col) or f"recorded in {name}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    reasons = journalled(a.audit)
    src_reasons = source_journalled(a.audit)
    total = 0
    explained: list[tuple[str, str]] = []
    by_source: list[tuple[str, str]] = []
    unexplained: list[tuple[str, str]] = []

    with open(a.manifest, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if len(r) < 2:
                continue
            total += 1
            dest, src = r[0], r[1]
            if os.path.exists(lp(dest)):
                continue
            if dest in reasons:
                explained.append((dest, src))
            elif src in src_reasons:
                by_source.append((dest, src))
            else:
                unexplained.append((dest, src))

    if not a.quiet:
        print(f"{total:,} manifest rows")
        gone = len(explained) + len(by_source) + len(unexplained)
        print(f"  {total - gone:,} present")
        print(f"  {len(explained):,} gone, journalled at the library")
        print(f"  {len(by_source):,} gone, only the source was journalled")
        print(f"  {len(unexplained):,} gone, NOT journalled anywhere")
        if explained:
            print("\nJournalled removals:")
            for dest, _ in explained:
                print(f"  {dest}\n     {reasons[dest][:96]}")
        if by_source:
            print("\nSource journalled, library removal not recorded:")
            for dest, src in by_source:
                print(f"  {os.path.basename(dest)}  -  {src_reasons[src][:60]}")
            print("\nThese were almost certainly removed by the same cleanup that")
            print("took their originals, but nothing recorded it at the library end.")
        if unexplained:
            print("\nUNEXPLAINED - a file left the library with no record of why:")
            for dest, src in unexplained:
                print(f"  {dest}\n     came from: {src[:96]}")
            print("\nCheck this against the deletion journals and LEARNINGS.md rule 1")
            print("before assuming it is benign.")

    sys.exit(1 if unexplained else 0)


if __name__ == "__main__":
    main()
