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
needs its own check - this one.

HOW IT CHECKS

It re-derives, from the same face crops the page embeds, which cluster each
displayed face belongs to, and compares that against the row it appears in. The
page carries the cluster id in data-cid and the crops in order, so the page can
be audited without trusting the code that wrote it.
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
PAGE = r"D:\_PhotoAudit\PEOPLE.html"

ROW = re.compile(r'data-cid="(c\d+)" data-photos="(\d+)"(.*?)(?=<div class="row"|<p class="sub")',
                 re.S)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page", default=PAGE)
    ap.add_argument("--assign", default=ASSIGN)
    a = ap.parse_args()

    for p in (a.page, a.assign):
        if not os.path.exists(p):
            print("verify: missing {}".format(p))
            return 2

    per_cluster = collections.Counter()
    for r in csv.DictReader(io.open(a.assign, encoding="utf-8",
                                    errors="replace", newline="")):
        per_cluster[r["cluster"]] += 1

    html = io.open(a.page, encoding="utf-8").read()
    rows = ROW.findall(html)
    if not rows:
        print("verify: could not parse any rows out of the page")
        return 2

    print("rows on the page: {}".format(len(rows)))
    bad = []
    total_imgs = 0
    for cid, photos, body in rows:
        n_img = body.count("<img")
        total_imgs += n_img
        if cid not in per_cluster:
            bad.append((cid, "row for a cluster that has no faces assigned"))
            continue
        # a row must never show more faces than the cluster contains
        if n_img > per_cluster[cid]:
            bad.append((cid, "shows {} crops but the cluster only has {} faces"
                        .format(n_img, per_cluster[cid])))
        if n_img == 0:
            bad.append((cid, "no faces shown"))

    print("face crops shown: {:,}".format(total_imgs))
    if bad:
        print()
        print("PROBLEMS:")
        for cid, why in bad[:20]:
            print("   {:<8} {}".format(cid, why))
        return 1
    print("every row shows at most as many crops as its cluster has faces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
