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
clusters - is derived and can be rebuilt. So they go through stages/07_people/answers.py:
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
import shutil
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
HERE = os.path.dirname(os.path.abspath(__file__))

from answers import Journal                                      # noqa: E402

TAGS = r"D:\_enrichment\content_tags.csv"
# A second copy of the journal, off the library disk. It is the only data in the
# project compute cannot reproduce, and until 2026-09-15 it lived on one drive.
BACKUP = r"G:\My Drive\Personal\Family\Photo library - answers backup"
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
    ap.add_argument("--sheet", default="",
                    help="the PEOPLE.html these answers came from. Every row on it "
                         "that is not named here is recorded as declined, so it is "
                         "never shown again")
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

    pairs, bad, unknown, unreadable, declined = [], [], [], [], []
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        m = LINE.match(ln)
        if not m:
            bad.append((ln.strip(), "could not read a cluster id and a name"))
            continue
        cid, name = m.group(1), m.group(2).strip()
        # A dash is the skip button, and it USED to be dropped here. That is why
        # Krish was shown the same faces four rounds running: a refusal that is
        # not written down is indistinguishable from a question never asked, and
        # the sheet only hides what the journal knows about. It is an answer.
        if name in ("-", "--", "skip"):
            declined.append((cid, known.get(cid, 0), "skipped on the sheet"))
            continue

        # A trailing " - ..." is a remark, not part of the name. Recording
        # "Adam Goodman - some are the backs of peoples heads" as a PERSON would
        # put that whole string on every photograph in the cluster.
        note = ""
        if " - " in name:
            name, note = name.split(" - ", 1)
            name, note = name.strip(), note.strip()

        if not name:
            bad.append((ln.strip(), "a remark with no name in front of it"))
            continue
        # checked before the question and verdict branches too: a typo that
        # queues a question against a cluster that does not exist is lost quietly
        if cid not in known:
            bad.append((ln.strip(), "no such cluster - a typo would label the "
                                    "wrong person's photographs"))
            continue

        # "?" is not a name, it is the absence of one. Recording it as a person
        # would create a human answer called "?" that outranks every model for
        # ever and would have to be found and unpicked later. It is recorded as
        # a question to ask instead.
        #
        # "for Bharti" is not a name either: it hands the question to someone who
        # was there. Recorded as needs_identifying=Bharti, so the game knows whose
        # queue it belongs in - never as a person called "for Bharti".
        low = name.lower()
        ask = re.match(r"^for\s+(\S.*)$", name, re.I)
        if low in ("?", "??", "unknown", "unsure") or ask:
            who = ask.group(1).strip() if ask else "yes"
            who = who[:1].upper() + who[1:]
            unknown.append((cid, known[cid], who, note))
            continue

        # "Unsure, blurry" is a verdict, not a deferral: nobody will be able to
        # say who this is. Recorded as unidentifiable, so it is never asked again
        # and never handed to the game either.
        if low.startswith("unsure") or low in ("blurry", "unidentifiable"):
            unreadable.append((cid, known[cid], low, note))
            continue
        pairs.append((cid, name, known[cid], note))

    if bad:
        print()
        print("REFUSED {} line(s):".format(len(bad)))
        for ln, why in bad:
            print("   {:<34} {}".format(ln[:34], why))

    # EVERY ROW SHOWN AND NOT NAMED IS A REFUSAL, and refusals are answers.
    #
    # Krish, 2026-09-16: "Stop resending me batches I have refused to identify -
    # they are unidentifiable." Measured when he said it: 186 rows had been shown
    # across four sheets and 60 were never answered, so each new sheet re-showed
    # faces he had already passed over - twice, in some cases. people_sheet only
    # skips what the journal holds, and a blank row reached the journal as
    # nothing at all.
    if a.sheet:
        if not os.path.exists(a.sheet):
            print("STOPPING: no sheet at {} - without it, rows you left blank "
                  "would be shown again".format(a.sheet))
            return 1
        html = io.open(a.sheet, encoding="utf-8", errors="replace").read()
        rows_on_sheet = re.findall(r'data-cid="(c\d+)"', html)
        if not rows_on_sheet:
            print("STOPPING: no rows parsed out of {}".format(a.sheet))
            return 1
        named_here = {c for c, _, _, _ in pairs} | {c for c, _, _, _ in unknown} \
            | {c for c, _, _, _ in unreadable} | {c for c, _, _ in declined}
        for cid in rows_on_sheet:
            if cid not in named_here:
                declined.append((cid, known.get(cid, 0), "shown and not named"))

    if not (pairs or unknown or unreadable or declined):
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
        print("{} NOT YET IDENTIFIED - recorded as a question to ask, never as a "
              "person called \"?\":".format(len(unknown)))
        for cid, n, who, note in unknown:
            print("   {:<8} {:>6,} faces   ask: {}".format(
                cid, n, "anyone" if who == "yes" else who))

    if unreadable:
        print()
        print("{} UNIDENTIFIABLE - never asked again, never offered to the game:"
              .format(len(unreadable)))
        for cid, n, verdict, note in unreadable:
            print("   {:<8} {:>6,} faces   {}".format(cid, n, verdict))

    if declined:
        print()
        print("{} DECLINED - shown and not named, so never shown again:".format(
            len(declined)))
        for cid, n, why in declined[:12]:
            print("   {:<8} {:>6,} faces   {}".format(cid, n, why))
        if len(declined) > 12:
            print("   ... and {} more".format(len(declined) - 12))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    j = Journal(a.store)
    for cid, name, _, note in pairs:
        j.record("cluster", cid, "person", name, note=note)
    for cid, n, who, note in unknown:
        # not a name: a question, recorded so the game can ask it - and of whom
        j.record("cluster", cid, "needs_identifying", who, note=note)
    for cid, n, verdict, note in unreadable:
        j.record("cluster", cid, "unidentifiable", verdict, note=note)
    for cid, n, why in declined:
        j.record("cluster", cid, "unidentifiable", "declined", note=why)
    print()
    print("recorded {} names, {} questions, {} unidentifiable, {} declined to {}".format(
        len(pairs), len(unknown), len(unreadable), len(declined), j.path))
    try:
        os.makedirs(BACKUP, exist_ok=True)
        shutil.copyfile(j.path, os.path.join(BACKUP, "answers.csv"))
        print("backed up the journal to {}".format(BACKUP))
    except OSError as e:
        # loud, not fatal: the answer IS recorded, it just has one copy
        print("WARNING: journal NOT backed up to {}: {}".format(BACKUP, e))
    print("rebuild the index to see them on the photographs:")
    print("    python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
