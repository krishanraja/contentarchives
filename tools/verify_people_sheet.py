r"""Check every face shown on PEOPLE.html belongs to the row it is shown in.

    python verify_people_sheet.py     # 0 correct, 1 wrong, 2 can't tell

WHY THIS EXISTS

The clustering was verified and was right: the twelve biggest clusters had
within-cluster cosine of 0.48-0.61 against a different-people baseline of 0.049,
with no sign of a merge. Then the page rendered from it showed six or seven
different people per row, and Krish found that by looking at it.

The bug was not in the data. people_sheet.py read the tag store, which records
"this PHOTOGRAPH contains c14" and cannot say WHICH face in it is c14, so it drew
every face in every photograph the cluster touched and sorted by detection score.
Measured afterwards: the candidate pool was 66-76% other people, and 11 of the 12
crops displayed for c14 were not in c14 at all.

So verifying the clustering was necessary and nowhere near sufficient. What a
person looks at is a SEPARATE ARTEFACT from the data it was built out of, and it
needs its own check - this one (learning 48).

HOW IT CHECKS

Every crop carries data-face="hash:frame:face_index", naming the exact face it
was cut from. Each one is looked up in the assignment files - FACE-CLUSTERS.csv
for photographs, FACE-CLUSTERS-VIDEO.csv for video frames - mapped to its merged
group through CLUSTER-MERGES.csv, and compared with the row it sits in. So the
page is audited against the data, not against the code that drew it.

The first version only counted crops per row. That could not see a crop from the
wrong person, and after merging it compared a GROUP's row against one cluster's
face count. A crop with no data-face cannot be checked at all and fails: a page
from an older generator must be rebuilt, not waved through.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sys

ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
VIDEO_ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv"
MERGES = r"D:\_PhotoAudit\CLUSTER-MERGES.csv"
PAGE = r"D:\_PhotoAudit\PEOPLE.html"

ROW = re.compile(r'data-cid="(c\d+)" data-photos="(\d+)"(.*?)(?=<div class="row"|<p class="sub")',
                 re.S)
FACE = re.compile(r'<img data-face="([0-9a-f]{64}):([^":]*):(-?\d+)"')


def rows_of(p: str):
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        yield from csv.DictReader(f)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page", default=PAGE)
    ap.add_argument("--assign", default=ASSIGN)
    ap.add_argument("--video-assign", default=VIDEO_ASSIGN)
    ap.add_argument("--merges", default=MERGES)
    a = ap.parse_args()

    for p in (a.page, a.assign):
        if not os.path.exists(p):
            print("verify: missing {}".format(p))
            return 2

    group_of = {}
    if os.path.exists(a.merges):
        for r in rows_of(a.merges):
            group_of[r["cluster"]] = r["group"]

    cluster_of = {}
    for r in rows_of(a.assign):
        cluster_of[(r["hash"], "", str(r["face_index"]))] = r["cluster"]
    if os.path.exists(a.video_assign):
        for r in rows_of(a.video_assign):
            cluster_of[(r["hash"], r["image"], str(r["face_index"]))] = r["cluster"]
    per_group = collections.Counter(group_of.get(c, c) for c in cluster_of.values())

    html = io.open(a.page, encoding="utf-8").read()
    rows = ROW.findall(html)
    if not rows:
        print("verify: could not parse any rows out of the page")
        return 2

    print("rows on the page: {}".format(len(rows)))
    bad = []
    total = 0
    for cid, photos, body in rows:
        n_img = body.count("<img")
        faces = FACE.findall(body)
        total += n_img
        if n_img == 0:
            bad.append((cid, "no faces shown"))
            continue
        if len(faces) != n_img:
            bad.append((cid, "{} of {} crops say which face they are - the rest "
                        "cannot be checked".format(len(faces), n_img)))
        if n_img > per_group[cid]:
            bad.append((cid, "shows {} crops but its group only has {} faces".format(
                n_img, per_group[cid])))
        seen = set()
        for h, image, idx in faces:
            c = cluster_of.get((h, image, idx))
            if c is None:
                bad.append((cid, "crop of {}{} face {} is in no assignment file".format(
                    h[:12], (" " + image[-12:]) if image else "", idx)))
            elif group_of.get(c, c) != cid:
                bad.append((cid, "crop of a {} face (group {}) shown in this row".format(
                    c, group_of.get(c, c))))
            if h in seen:
                bad.append((cid, "the same photograph or video appears twice"))
            seen.add(h)

    print("face crops shown: {:,}".format(total))
    if bad:
        print()
        print("PROBLEMS ({}):".format(len(bad)))
        for cid, why in bad[:20]:
            print("   {:<8} {}".format(cid, why))
        return 1
    print("every crop is a face assigned to the row it is shown in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
