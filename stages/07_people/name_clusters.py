r"""Every cluster labelled with a given name, so "which of these is which" is asked once.

    python name_clusters.py --like Rishi
    python name_clusters.py --like Kiran --sheet D:\_PhotoAudit\RISHI.html

WHY THIS EXISTS

Krish, 2026-09-17: "I have labelled two different people Kiran, one of them
should be Kiran Nathwani." Then, a round later: "I think we need to redo the
Rishi's the same way we redid the Kiran's." The same question will keep coming,
because one name genuinely belongs to two people and a face cluster cannot know
that.

The Kiran answer was found with a throwaway script in a session scratchpad.
Writing a second one for Rishi is how five near-identical profile scripts
accumulated across rounds 13-15, and how check_repeats.py came to carry a stale
`PEOPLE-round[1-6]` pattern for three rounds while reporting every sheet clean.
So: one tool, in the repo, that takes the name.

WHAT IT REPORTS, AND WHY EACH PART MATTERS

  - every journal row whose person value contains the fragment, in recorded
    order, so a later answer that already corrected an earlier one is visible
  - the MERGE GROUP of each cluster. merge_clusters refuses to mix two
    differently-named clusters, so clusters sharing a group have been judged the
    same person by the embeddings, and clusters NOT sharing one have not
  - photographs covered, the year span, and the Personal/Communal split - the
    context that makes a disambiguation page readable rather than two grids of
    faces

WHAT IT REFUSES TO DO

Decide. On the Kiran question the counts and dates pointed the wrong way: the
157-photograph fourteen-year cluster turned out to be Nathwani and a small
eleven-photograph cluster was the other person. Inferring it would have renamed
a real person across 157 photographs, and nothing in the data would have
objected. This prints the evidence and the exact `people_sheet.py --clusters`
command to put the faces in front of Krish (learning 54).
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                                # noqa: E402

JOURNAL = os.path.join(r"D:\_enrichment", "answers.csv")
MERGES = os.path.join(P.AUDIT, "CLUSTER-MERGES.csv")
ASSIGN = os.path.join(P.AUDIT, "FACE-CLUSTERS.csv")
VIDEO_ASSIGN = os.path.join(P.AUDIT, "FACE-CLUSTERS-VIDEO.csv")


def side_of(path):
    """Personal, Communal, or neither - from the path, never files.side."""
    p = (path or "").lower().replace("/", "\\")
    if "\\media\\personal\\" in p:
        return "Personal"
    if "\\media\\communal\\" in p:
        return "Communal"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--like", required=True,
                    help="name fragment, case-insensitive (e.g. Rishi)")
    ap.add_argument("--journal", default=JOURNAL)
    ap.add_argument("--merges", default=MERGES)
    ap.add_argument("--assign", default=ASSIGN)
    ap.add_argument("--video-assign", default=VIDEO_ASSIGN)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--sheet", default="",
                    help="if given, print the people_sheet.py command that "
                         "builds a disambiguation page at this path")
    a = ap.parse_args()

    if not os.path.isfile(a.journal):
        print("STOPPING: no answers journal at {}".format(a.journal))
        return 1
    frag = a.like.lower()

    rows = []
    with io.open(a.journal, encoding="utf-8", newline="") as fh:
        for i, r in enumerate(csv.DictReader(fh)):
            if r.get("field") != "person":
                continue
            if frag in (r.get("value") or "").lower():
                rows.append((i, r))

    print("=== journal rows whose person contains {!r}, in recorded order ===".format(a.like))
    for i, r in rows:
        print("  row {:<5} {:<9} {:<24} who={:<8} when={}".format(
            i, r.get("target", ""), repr(r.get("value", "")),
            r.get("who", ""), r.get("when", "")))
    if not rows:
        print("  (none)")
        return 0

    # A cluster answered twice keeps only its LATEST answer, because the journal
    # is append-only and a later human answer outranks an earlier one. Showing
    # every row above is deliberate - the history is how a correction is seen -
    # but the current state is the last row per target.
    latest = {}
    for i, r in rows:
        latest[r["target"]] = r["value"]
    print()
    print("=== current state, one row per cluster ===")
    by_name = collections.defaultdict(list)
    for target, value in sorted(latest.items()):
        by_name[value].append(target)
    for value, targets in sorted(by_name.items()):
        print("  {:<26} {}".format(repr(value), ", ".join(sorted(targets))))

    group_of = {}
    if os.path.exists(a.merges):
        for r in csv.DictReader(io.open(a.merges, encoding="utf-8", newline="")):
            group_of[r["cluster"]] = r["group"]

    faces = collections.defaultdict(set)
    for path in (a.assign, a.video_assign):
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(io.open(path, encoding="utf-8",
                                        errors="replace", newline="")):
            if r.get("bbox"):
                faces[group_of.get(r["cluster"], r["cluster"])].add(r["hash"])

    years, paths_by_hash = {}, {}
    try:
        import sqlite3
        db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")),
                             uri=True)
        try:
            for h, y in db.execute("select hash, min(year) from files "
                                   "where hash is not null and year!='' "
                                   "group by hash"):
                years[h] = y
            for h, p in db.execute("select hash, path from files "
                                   "where hash is not null"):
                paths_by_hash[h] = p
        finally:
            db.close()
    except Exception as e:                                       # noqa: BLE001
        print()
        print("WARNING: could not read {} ({}), so spans and sides are blank"
              .format(a.db, e))

    print()
    print("=== each cluster: group, reach, span, side ===")
    print("  {:<9} {:<10} {:>7}  {:<11} {}".format(
        "cluster", "group", "photos", "span", "side"))
    for target in sorted(latest, key=lambda t: -len(faces.get(group_of.get(t, t), ()))):
        g = group_of.get(target, target)
        hs = faces.get(g, set())
        ys = sorted(y for y in (years.get(h) for h in hs) if y)
        span = "{}-{}".format(ys[0], ys[-1]) if ys else "?"
        sides = collections.Counter(side_of(paths_by_hash.get(h)) for h in hs)
        print("  {:<9} {:<10} {:>7,}  {:<11} {}".format(
            target, g + ("" if target in group_of else " *"), len(hs), span,
            dict(sides)))
    print("  (* = unmerged: the embeddings have not judged it the same as any other)")

    shared = collections.Counter(group_of.get(t, t) for t in latest)
    both = [g for g, n in shared.items() if n > 1]
    print()
    print("  clusters sharing a merge group: {}".format(both or "none"))

    print()
    print("=== NOT DECIDING. Put the faces in front of Krish ===")
    ids = ",".join(sorted(latest))
    out = a.sheet or os.path.join(P.AUDIT, "{}.html".format(a.like.upper()))
    print("  python stages/07_people/people_sheet.py \\")
    print("      --clusters {} \\".format(ids))
    print("      --include-named --include-communal --out {}".format(out))
    print()
    print("  Then gate it with verify_people_sheet.py before he sees it, and")
    print("  record his answer as NEW journal rows - never an edit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
