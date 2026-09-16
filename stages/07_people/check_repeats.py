r"""Does a new naming sheet re-show a row Krish has already been offered?

    python stages\07_people\check_repeats.py <sheets dir> <new sheet>

Exit 0 when every row is new, 1 when anything repeats.

WHY

Krish, 2026-09-16: "Stop resending me batches I have refused to identify - they
are unidentifiable." A cluster he was shown and chose not to name is an ANSWER,
not an absence of one, and re-offering it wastes the only thing in this project
that compute cannot reproduce.

`record_people.py --sheet` is what records those refusals, and `people_sheet.py`
excludes answered and declined clusters at source. This asserts the RESULT
against the sheets themselves rather than trusting either of them - the sheets
are what he actually saw.

THE BUG THIS FILE CARRIES AS A SCAR

It matched `PEOPLE-round[1-6].html` until 2026-09-16. Written when round 7 was
the next sheet, never widened: rounds 7, 8 and 9 were invisible to it, so its
"rows shown in earlier ones" sat frozen at 186 for three consecutive runs while
each new sheet was reported clean. Rounds 7-10 turned out to be genuinely clean,
so the verdicts held - but that is luck, not rigour (learning 55). It also lived
in a session scratch directory, which is how a guard comes to have a stale
hardcoded range in the first place.

Clusters merge, so a row is compared by its MERGE GROUP, not its raw id: the
same person under a new cluster id is still a repeat.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                                # noqa: E402

# Any round, however many there are. NEVER a bounded range: see the scar above.
SHEET = re.compile(r"PEOPLE-round\d+\.html$")

# Fixtures that live beside real sheets and must not pollute the baseline. Named
# explicitly, because excluding them by digits is what created the bug.
FIXTURES = {"PEOPLE-tampered.html", "PEOPLE-verifytest.html"}


def merge_groups(merges: str | None = None) -> dict[str, str]:
    """cluster id -> merge group, so a renumbered cluster is still recognised."""
    path = merges or os.path.join(P.AUDIT, "CLUSTER-MERGES.csv")
    group: dict[str, str] = {}
    if os.path.exists(path):
        for r in csv.DictReader(io.open(path, encoding="utf-8", newline="")):
            group[r["cluster"]] = r["group"]
    return group


def rows_of(path: str, group: dict[str, str] | None = None) -> list[str]:
    """The cluster rows a sheet shows, as merge groups."""
    group = group if group is not None else {}
    html = io.open(path, encoding="utf-8", errors="replace").read()
    return [group.get(c, c) for c in re.findall(r'data-cid="(c\d+)"', html)]


def earlier_sheets(d: str, new: str) -> list[str]:
    """Every sheet in `d` except the fixtures and the sheet under test."""
    out = []
    for fn in sorted(os.listdir(d)):
        if fn in FIXTURES:
            continue
        if os.path.abspath(os.path.join(d, fn)) == os.path.abspath(new):
            continue
        if SHEET.match(fn):
            out.append(fn)
    return out


def repeats(d: str, new: str, merges: str | None = None):
    """-> (repeated groups, rows on the new sheet, rows seen before, sheets read)"""
    group = merge_groups(merges)
    sources = earlier_sheets(d, new)
    seen: set[str] = set()
    for fn in sources:
        seen |= set(rows_of(os.path.join(d, fn), group))
    rows = rows_of(new, group)
    return sorted(set(rows) & seen), rows, seen, sources


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    d, new = argv[0], argv[1]
    dup, rows, seen, sources = repeats(d, new)
    print("earlier sheets read       : {}  {}".format(
        len(sources), ", ".join(sources)))
    print("rows on the new sheet     : {}".format(len(rows)))
    print("rows shown in earlier ones: {}".format(len(seen)))
    print("repeats                   : {}  {}".format(len(dup), dup[:10]))
    print("VERDICT: {}".format("CLEAN - every row is new" if not dup
                               else "STILL REPEATING - the fix did not hold"))
    return 1 if dup else 0


if __name__ == "__main__":
    sys.exit(main())
