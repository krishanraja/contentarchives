r"""Take answers from the phone games into the journal. Safe to run twice, or fifty times.

    python ingest_game_answers.py --rows rows.json            # dry run
    python ingest_game_answers.py --rows rows.json --apply
    python ingest_game_answers.py --rows rows.json --who bharti --apply

WHY THIS EXISTS

Krish, 2026-09-18: *"you need to account for the fact that this session might be
closed when I am on my phone doing the classification game, and that there are
likely to be a lot of repeated names. make it antifragile, perhaps on a biweekly
basis you can auto check for new data and integrate it safely"*.

So the game cannot depend on a live session. Answers land in the artifact's
shared database; a scheduled chain wakes Claude, which reads that database with
its own tool - that part cannot be a CLI - dumps the rows to JSON, and hands
them here. Everything from the JSON onwards is ordinary, testable Python.

WHAT "SAFE TO RUN TWICE" MEANS

Every row carries an id from the artifact db. This keeps a CURSOR of the ids
already ingested, so a re-read never records the same answer twice. The journal
is append-only and a duplicate would be harmless but noisy - and noise in the
one file compute cannot reproduce is worth avoiding.

The cursor lives beside the journal, not in the repo, and losing it is
recoverable: the worst case is duplicate rows with identical values, not a lost
or altered answer.

REPEATED NAMES ARE PREVENTED AT SOURCE, AND REPAIRED HERE

The game autocompletes from the names already in the journal, so "Lauren" is
picked rather than typed. This is the second line: a name that differs from a
known one only by case, spacing or punctuation is folded onto the known one, and
anything else is recorded as typed. It will not guess at spelling - "Laurenn"
stays "Laurenn", because the two Kirans and the three Rishis are what happens
when a machine decides two names are one person.

WHAT IT REFUSES

  - a cluster id that is not in the tag store (record_people.py's rule: a typo
    would label somebody else's photographs and look like success)
  - "?" and "for <who>", which are questions rather than names
  - a value longer than a name, which is a sentence that arrived in a text box
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import os
import re
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
from answers import Journal                                      # noqa: E402

STORE = r"D:\_enrichment"
TAGS = os.path.join(STORE, "content_tags.csv")
CURSOR = os.path.join(STORE, "game-ingest-cursor.json")
ASK = re.compile(r"^for\s+(\S.*)$", re.I)
FOLD = re.compile(r"[^a-z0-9]+")


def known_clusters(tags: str) -> set:
    out = set()
    if not os.path.exists(tags):
        return out
    with io.open(tags, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("tag") == "cluster" and r.get("value"):
                out.add(r["value"])
    return out


def known_names(journal: Journal) -> dict:
    """folded name -> the spelling already in the journal, latest wins."""
    out = {}
    for r in journal.all_rows():
        if r.get("field") == "person" and r.get("value"):
            v = r["value"].strip()
            if v and not v.lower().startswith(("for ", "unsure")):
                out[FOLD.sub("", v.lower())] = v
    return out


def canonical(name: str, known: dict) -> tuple:
    """(spelling to record, whether it was folded onto an existing name).

    Folds only on an EXACT match after removing case, spaces and punctuation:
    "lauren" and "Lauren " become "Lauren". Never on similarity - "Laurenn"
    stays "Laurenn". A machine deciding two names are one person is how the two
    Kirans and the three Rishis happened.
    """
    key = FOLD.sub("", name.strip().lower())
    hit = known.get(key)
    if hit and hit != name.strip():
        return hit, True
    return name.strip(), False


def load_cursor(path: str) -> set:
    if not os.path.exists(path):
        return set()
    try:
        with io.open(path, encoding="utf-8") as fh:
            return set(json.load(fh).get("ingested", []))
    except (ValueError, OSError):
        # A corrupt cursor must not stop the ingest: the worst it costs is
        # duplicate rows with identical values, and the journal survives that.
        print("  (cursor unreadable - treating every row as new)")
        return set()


def save_cursor(path: str, ids: set) -> None:
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"ingested": sorted(ids)}, fh, indent=1)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True,
                    help="JSON from the artifact db: a list of "
                         "{id, cluster, name} objects")
    ap.add_argument("--store", default=STORE)
    ap.add_argument("--tags", default=TAGS)
    ap.add_argument("--cursor", default=CURSOR)
    ap.add_argument("--who", default="krish",
                    help="whose answers these are - both games write ONE "
                         "journal, so provenance is not optional")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.rows):
        print("STOPPING: no rows at {}".format(a.rows))
        print("  An empty ingest and a missing file look identical to a check")
        print("  that only counts what it recorded.")
        return 1
    with io.open(a.rows, encoding="utf-8") as fh:
        rows = json.load(fh)
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("answers") or []
    print("rows from the game : {:,}".format(len(rows)))

    seen = load_cursor(a.cursor)
    print("already ingested   : {:,}".format(len(seen)))
    known = known_clusters(a.tags)
    journal = Journal(a.store, who=a.who)
    names = known_names(journal)
    print("clusters in store  : {:,}".format(len(known)))
    print("names already known: {:,}".format(len(names)))

    fresh, skipped, refused, folded = [], 0, [], []
    for r in rows:
        rid = str(r.get("id") or "")
        cid = str(r.get("cluster") or r.get("cid") or "").strip()
        raw = str(r.get("name") or r.get("value") or "").strip()
        if rid and rid in seen:
            skipped += 1
            continue
        if not cid or not raw:
            refused.append((rid, cid, raw, "no cluster or no name"))
            continue
        if cid not in known:
            refused.append((rid, cid, raw, "no such cluster in the tag store"))
            continue
        if len(raw) > 60:
            refused.append((rid, cid, raw[:40], "that is a sentence, not a name"))
            continue
        low = raw.lower()
        # A SKIP IS AN ANSWER, and the most consequential one: it means never
        # show me this again. record_people.py has read '-' that way since round
        # 14 ("Stop resending me batches I have refused to identify"), and the
        # game had no way to say it at all - so every skipped face came back in
        # the next batch. Krish, on seeing that: "If I'm skipping, I don't care
        # that they never end up classified and you need to be ok with that."
        if low in ("-", "--", "skip", "skipped"):
            fresh.append((rid, cid, "unidentifiable", "declined"))
            continue
        if low in ("?", "??", "unknown", "unsure") or ASK.match(raw):
            who = ASK.match(raw).group(1).strip() if ASK.match(raw) else "yes"
            fresh.append((rid, cid, "needs_identifying",
                          who[:1].upper() + who[1:]))
            continue
        if low.startswith("unsure") or low in ("blurry", "unidentifiable"):
            fresh.append((rid, cid, "unidentifiable", low))
            continue
        name, was_folded = canonical(raw, names)
        if was_folded:
            folded.append((raw, name))
        fresh.append((rid, cid, "person", name))

    print()
    print("  new answers      : {:,}".format(len(fresh)))
    print("  already ingested : {:,}".format(skipped))
    print("  refused          : {:,}".format(len(refused)))
    if folded:
        print("  folded onto a name already in the journal: {:,}".format(
            len(folded)))
        for was, now in folded[:8]:
            print("     {!r} -> {!r}".format(was, now))
    for rid, cid, raw, why in refused[:8]:
        print("     REFUSED {:<10} {!r:<22} {}".format(cid, raw[:22], why))

    by_field = collections.Counter(f for _, _, f, _ in fresh)
    if fresh:
        print("  {}".format(dict(by_field)))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    for rid, cid, field, value in fresh:
        journal.record("cluster", cid, field, value,
                       note="from the {} game".format(a.who))
        if rid:
            seen.add(rid)
    save_cursor(a.cursor, seen)
    print()
    print("recorded {:,} answers as who={!r}".format(len(fresh), a.who))
    print("cursor now holds {:,} ingested ids: {}".format(len(seen), a.cursor))
    print("rebuild the index to see them on the photographs:")
    print("    python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
