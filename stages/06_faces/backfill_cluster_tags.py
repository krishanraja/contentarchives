r"""Give every assigned face a cluster tag, so nothing is unnameable.

    python backfill_cluster_tags.py            # report only
    python backfill_cluster_tags.py --apply

WHY THIS EXISTS

cluster_faces.py writes a tag only for a cluster of two or more faces - "a
cluster of one is not yet a person" - while FACE-CLUSTERS.csv holds every face,
40,006 singletons among them. Three things read the smaller set and one reads
the larger:

    people_sheet.py     ranks from the ASSIGNMENT files    (58,786 groups)
    record_people.py    validates against the TAG store    (19,604 clusters)
    build_db.py         expands a cluster answer through the TAG store

So a sheet could offer a row that could not be recorded and would have labelled
nothing anyway. Round 19, 2026-09-17: five rows Krish answered came back "no
such cluster", and the decline pass would then have recorded his answers as
refusals.

Asked how to resolve it, he chose: "we should try to classify everything, but
don't ask me again if I skip once". So every assigned face gets a tag, the
sheet can offer anything, and a row he skips is recorded as declined exactly as
it is today - which only works once the cluster exists in the store.

WHAT IT IS NOT

It does not re-cluster, and it never touches FACE-CLUSTERS.csv - the cluster ids
are FROZEN. It only publishes, into the derived tag store, assignments that are
already recorded on disk. Its own `source` marks the backfill, so it can be told
apart from what cluster_faces.py wrote.
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
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from store import Store                                          # noqa: E402

SOURCE = "faces-backfill"


def iter_csv(p: str):
    """Streamed: content_tags.csv is well over a million rows (learning 9)."""
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        yield from csv.DictReader(f)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--assign", default=os.path.join(P.AUDIT, "FACE-CLUSTERS.csv"))
    ap.add_argument("--video-assign",
                    default=os.path.join(P.AUDIT, "FACE-CLUSTERS-VIDEO.csv"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    tags_csv = os.path.join(a.store, "content_tags.csv")
    if not os.path.exists(tags_csv):
        print("STOPPING: no tag store at {}".format(tags_csv))
        print("  An empty store and a missing one look identical to a check that")
        print("  only asks whether a file exists, and the difference here is")
        print("  whether this writes 58,786 clusters or repairs 40,006.")
        return 1

    have_pair, tagged = set(), set()
    for r in iter_csv(tags_csv):
        if r.get("tag") == "cluster":
            have_pair.add((r["hash"], r["value"]))
            tagged.add(r["value"])
    print("clusters already in the store : {:,}".format(len(tagged)))

    faces = collections.defaultdict(list)
    for path in (a.assign, a.video_assign):
        if not os.path.exists(path):
            print("  (no {})".format(os.path.basename(path)))
            continue
        for r in iter_csv(path):
            if r.get("bbox"):
                faces[r["cluster"]].append(r)
    print("clusters in the assignments   : {:,}".format(len(faces)))

    rows, clusters_added = [], set()
    for cid, rs in faces.items():
        for r in rs:
            if (r["hash"], cid) in have_pair:
                continue
            try:
                conf = float(r.get("det_score") or 1.0)
            except ValueError:
                conf = 1.0
            rows.append((r["hash"], "cluster", cid, SOURCE, conf))
            if cid not in tagged:
                clusters_added.add(cid)

    sizes = collections.Counter(len(faces[c]) for c in clusters_added)
    print()
    print("face tags to write            : {:,}".format(len(rows)))
    print("clusters that become nameable : {:,}".format(len(clusters_added)))
    print("  of which singletons         : {:,}".format(sizes.get(1, 0)))
    print("  2+ faces                    : {:,}".format(
        sum(n for s, n in sizes.items() if s >= 2)))

    if not rows:
        print()
        print("nothing to do - every assigned face already has a tag.")
        return 0
    if not a.apply:
        print()
        print("report only. Re-run with --apply.")
        return 0

    st = Store(a.store)
    n = st.tag_many(rows)
    print()
    print("wrote {:,} cluster tags with source {!r}.".format(n, SOURCE))
    print("Rebuild the index for them to reach photographs:")
    print("    python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
