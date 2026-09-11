r"""Cluster _Review into decisions, not files.

29,092 files is weeks of scrolling and nobody will do it. That is a failure of
presentation: the same judgement is being asked thousands of times when it
could be asked once per pattern.

So this groups by the things a human actually decides on - where it came from,
what shape the filename is, what era it is, how big it is - and reports each
cluster with enough evidence to say keep-all or bin-all in one answer.

WHAT IT DELIBERATELY DOES NOT DO

It does not rank clusters by confidence and it does not recommend. A cluster of
6,000 forwarded images and a cluster of 6,000 photographs look identical from
here: both are JPEGs from a phone folder. The evidence that separates them is
visual, and this tool has no eyes. Its job is to make the QUESTION small enough
to answer, and to be honest that the answer is not in the metadata.

Where a cluster is genuinely mixed, that is reported as mixed rather than
guessed at, and it becomes a candidate for the vision pass or the swipe game
instead of a bulk decision.

    python review_patterns.py
    python review_patterns.py --min 100     # only clusters worth a decision
"""

from __future__ import annotations

import argparse
import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

JOURNAL = r"D:\_PhotoAudit\moved-to-review.csv"
ORIGIN_MAP = r"D:\_PhotoAudit\ORIGIN-MAP.csv"
OUT = r"D:\_PhotoAudit\REVIEW-CLUSTERS.csv"

SHAPES = [
    (re.compile(r"^screenshot[_-]", re.I), "screenshot"),
    (re.compile(r"^img-\d{8}-wa\d+", re.I), "whatsapp-received"),
    (re.compile(r"^(vid|video)-\d{8}-wa\d+", re.I), "whatsapp-video"),
    (re.compile(r"^(gh|gx|gopr)\d+", re.I), "gopro"),
    (re.compile(r"^(img|dsc|dscn)[_-]?\d+", re.I), "camera"),
    (re.compile(r"^\d{8}[_-]\d{6}"), "phone-timestamp"),
    (re.compile(r"^(fb_img|insta|received)", re.I), "social"),
    (re.compile(r"^(unnamed|image|photo|download)[\s_-]?\d*\.", re.I), "generic-name"),
    (re.compile(r"^[0-9a-f]{16,}\.", re.I), "hash-name"),
]


def shape(fn: str) -> str:
    for rx, name in SHAPES:
        if rx.match(fn):
            return name
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min", type=int, default=50)
    a = ap.parse_args()

    # where each file came from, so a cluster can be named by its source
    origin: dict[str, str] = {}
    if os.path.exists(ORIGIN_MAP):
        with open(ORIGIN_MAP, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                lp_ = P.resolve(r.get("LibraryPath", ""))
                if lp_:
                    origin[os.path.normcase(lp_)] = r.get("OriginFolder", "")

    # the move journal knows which files we put here, and why
    why: dict[str, str] = {}
    if os.path.exists(JOURNAL):
        with open(JOURNAL, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                if r.get("To"):
                    why[os.path.normcase(r["To"])] = r.get("Set", "")

    clusters: dict[tuple, list] = collections.defaultdict(list)
    total = 0
    for dp, dns, fns in os.walk(P.REVIEW):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            total += 1
            key = os.path.normcase(p)
            of = origin.get(key, "")
            leaf = of.replace("/", "\\").rstrip("\\").split("\\")[-1] if of else "(unknown origin)"
            clusters[(why.get(key, "pre-existing"), leaf, shape(fn))].append(sz)

    rows = []
    for (set_, leaf, sh), sizes in clusters.items():
        rows.append((len(sizes), sum(sizes), set_, leaf, sh))
    rows.sort(reverse=True)

    print(f"_Review holds {total:,} files\n")
    print(f"{'files':>7} {'GB':>7}  {'moved as':<18} {'origin folder':<34} shape")
    print("-" * 100)
    shown = 0
    for n, b, set_, leaf, sh in rows:
        if n < a.min:
            continue
        shown += n
        print(f"{n:>7,} {b/1024**3:>7.2f}  {set_:<18} {leaf[:33]:<34} {sh}")
    tail = total - shown
    print("-" * 100)
    print(f"{shown:>7,} in clusters of {a.min}+;  {tail:,} in smaller clusters")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Files", "Bytes", "MovedAs", "OriginFolder", "FilenameShape"])
        for n, b, set_, leaf, sh in rows:
            w.writerow([n, b, set_, leaf, sh])
    print(f"\nfull cluster list: {OUT}")
    print("\nA cluster's size tells you how much ONE answer is worth. It does not")
    print("tell you what the answer is - forwarded junk and real photographs look")
    print("identical from here. That part needs eyes.")


if __name__ == "__main__":
    main()
