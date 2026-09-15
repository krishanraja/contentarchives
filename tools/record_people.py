r"""Record the names from PEOPLE.html into the answers journal.

    python record_people.py --from-text "c14 = Mum
    c5 = Krish"

    python record_people.py --file names.txt
    python record_people.py --file names.txt --apply

Accepts what the Copy all answers button produces - `c14 = Mum`, one per line -
and also tolerates `c14: Mum`, `c14 Mum`, and stray blank lines, because a
person pasting from a browser should not have to think about format.

WHY THIS IS NOT JUST AN EDIT TO A CSV

The names are the only data in this project that money and compute cannot
reproduce. Everything else - thumbnails, hashes, classifications, embeddings,
clusters - is derived and can be rebuilt. So they go through engine/answers.py:
appended, never overwritten, provenance-stamped, and read by build_db which can
never write back to them.

A name is recorded against the CLUSTER, not against photographs. One row becomes
a label on every photograph that person appears in, and if the clustering is
later improved the same answer expands onto the new grouping without anybody
being asked again.

It refuses to record a cluster id that does not exist, because a typo that
silently records "c144" instead of "c14" would attach Mum to somebody else's
photographs and look exactly like a successful answer.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))

from answers import Journal                                      # noqa: E402

TAGS = r"D:\_enrichment\content_tags.csv"
LINE = re.compile(r"^\s*(c\d+)\s*[=:\t ]\s*(.+?)\s*$")


def known_clusters(tags: str) -> dict:
    counts = collections.Counter()
    if not os.path.exists(tags):
        return {}
    with io.open(tags, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("tag") == "cluster":
                counts[r["value"]] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-text", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--tags", default=TAGS)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    raw = a.from_text
    if a.file:
        raw = io.open(a.file, encoding="utf-8", errors="replace").read()
    if not raw.strip():
        print("nothing to record - pass --from-text or --file")
        return 2

    known = known_clusters(a.tags)
    print("clusters in the store: {:,}".format(len(known)))

    pairs, bad, unknown = [], [], []
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        m = LINE.match(ln)
        if not m:
            bad.append((ln.strip(), "could not read a cluster id and a name"))
            continue
        cid, name = m.group(1), m.group(2).strip()
        if name in ("-", "--", "skip"):
            continue

        # A trailing " - ..." is a remark, not part of the name. Recording
        # "Adam Goodman - some are the backs of peoples heads" as a PERSON would
        # put that whole string on every photograph in the cluster.
        note = ""
        if " - " in name:
            name, note = name.split(" - ", 1)
            name, note = name.strip(), note.strip()

        # "?" is not a name, it is the absence of one. Recording it as a person
        # would create a human answer called "?" that outranks every model for
        # ever and would have to be found and unpicked later. It is recorded as
        # a question to ask instead.
        if name in ("?", "??", "unknown", "unsure"):
            unknown.append((cid, known[cid] if cid in known else 0, note))
            continue
        if not name:
            bad.append((ln.strip(), "a remark with no name in front of it"))
            continue
        if cid not in known:
            bad.append((ln.strip(), "no such cluster - a typo would label the "
                                    "wrong person's photographs"))
            continue
        pairs.append((cid, name, known[cid], note))

    if bad:
        print()
        print("REFUSED {} line(s):".format(len(bad)))
        for ln, why in bad:
            print("   {:<34} {}".format(ln[:34], why))

    if not pairs:
        print()
        print("nothing recordable.")
        return 1

    reach = sum(n for _, _, n, _ in pairs)
    print()
    print("{} name(s), covering {:,} face tags:".format(len(pairs), reach))
    for cid, name, n, note in pairs:
        print("   {:<8} -> {:<24} {:>6,} faces{}".format(
            cid, name, n, ("   [" + note[:40] + "]") if note else ""))

    byname = collections.Counter(n for _, n, _, _ in pairs)
    dupes = [n for n, c in byname.items() if c > 1]
    if dupes:
        print()
        print("note: {} appears on more than one cluster - that is FINE and "
              "expected".format(", ".join(dupes)))
        print("      (the same person fragments across clusters by design; both "
              "answers stand)")

    if unknown:
        print()
        print("{} marked as NOT YET IDENTIFIED - recorded as a question,".format(len(unknown)))
        print("never as a person called \"?\":")
        for cid, n, note in unknown:
            print("   {:<8} {:>6,} faces".format(cid, n))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    j = Journal(a.store)
    for cid, name, _, note in pairs:
        j.record("cluster", cid, "person", name, note=note)
    for cid, n, note in unknown:
        # not a name: a question, recorded so the game can ask it
        j.record("cluster", cid, "needs_identifying", "yes", note=note)
    print()
    print("recorded {} answers to {}".format(len(pairs), j.path))
    print("rebuild the index to see them on the photographs:")
    print("    python tools/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
