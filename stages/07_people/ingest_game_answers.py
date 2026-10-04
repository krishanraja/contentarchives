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

STRUCTURED ROWS (the archives app, 2026-10-04)

The hosted app at archives.krishraja.com is played by several relatives, and
asks where a photograph was taken as well as who is in it. Its rows say what
they mean instead of being parsed from a string:

    {"id": ..., "scope": "cluster", "target": "c17", "field": "person",
     "value": "Asha Raja", "who": "bharti"}
    {"id": ..., "scope": "file", "target": "<hash>", "field": "place",
     "value": "Goa", "who": "bhasker"}

and only a WHITELIST of (scope, field) is accepted - see ALLOWED. Without it, a
row saying `sensitivity = none` would be applied by build_db.py with source
`human`, outrank the model, and publish a photograph the model had held back.
A file-scope row is accepted only for a hash in `--allowed` (the share set), so
a place cannot be written onto a photograph the app was never allowed to show.

Each row carries its own `who`, and is recorded under it: several people play
one app, and both games write ONE journal.

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
import unicodedata

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
from answers import BACKUP, Journal, backup_journal              # noqa: E402

STORE = r"D:\_enrichment"
TAGS = os.path.join(STORE, "content_tags.csv")
CURSOR = os.path.join(STORE, "game-ingest-cursor.json")
ASK = re.compile(r"^for\s+(\S.*)$", re.I)
# (scope, field) -> allowed values, or None for any value (still <= 60 chars).
ALLOWED = {
    ("cluster", "person"): None,
    ("cluster", "needs_identifying"): None,
    ("cluster", "unidentifiable"): {"declined", "mixed", "blurry"},
    ("file", "place"): None,
    ("file", "region"): None,
    ("file", "country"): None,
    # "Roughly what year?" for photographs with no clock. Its OWN field, never
    # `year`: a relative's "about 1985" must not be mistaken for a camera's
    # EXIF date, and build_db keeps it beside the real one, not over it.
    ("file", "approx_year"): None,
}
APPROX_YEAR = re.compile(r"^(18[5-9]\d|19\d\d|20\d\d)s?$")


def fold(name: str) -> str:
    """The key two spellings must share to be ONE name: case, spacing, punctuation.

    NFKC + casefold + letters and digits in ANY script. The ASCII pattern this
    replaced (`[^a-z0-9]+`) reduced every Devanagari name to "", so the second
    one ever recorded would have been folded onto the first - two different
    people silently made one, the exact failure folding exists to prevent.
    """
    s = unicodedata.normalize("NFKC", name or "").casefold()
    return "".join(ch for ch in s if ch.isalnum())


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
                k = fold(v)
                if k:
                    out[k] = v
    return out


def canonical(name: str, known: dict) -> tuple:
    """(spelling to record, whether it was folded onto an existing name).

    Folds only on an EXACT match after removing case, spaces and punctuation:
    "lauren" and "Lauren " become "Lauren". Never on similarity - "Laurenn"
    stays "Laurenn". A machine deciding two names are one person is how the two
    Kirans and the three Rishis happened.
    """
    key = fold(name)
    hit = known.get(key) if key else None
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


def load_allowed(path: str):
    """The share set, one hash per line, or None when not given."""
    if not path:
        return None
    with io.open(path, encoding="utf-8") as fh:
        return {ln.strip().lower() for ln in fh if ln.strip()}


def plan(rows, seen, known, names, who="krish", allowed=None):
    """(fresh, skipped, refused, folded) - pure, so a test reads the real logic.

    fresh   : [(rid, scope, target, field, value, who)]
    refused : [(rid, target, raw, why)]
    """
    fresh, skipped, refused, folded = [], 0, [], []
    for r in rows:
        rid = str(r.get("id") or "")
        if rid and rid in seen:
            skipped += 1
            continue
        row_who = str(r.get("who") or who).strip().lower() or who
        if r.get("field"):
            got = _structured(r, rid, row_who, known, names, allowed)
            if got[0] == "refused":
                refused.append(got[1])
            else:
                if got[2]:
                    folded.append(got[2])
                fresh.append(got[1])
            continue
        cid = str(r.get("cluster") or r.get("cid") or "").strip()
        raw = str(r.get("name") or r.get("value") or "").strip()
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
            fresh.append((rid, "cluster", cid, "unidentifiable", "declined", row_who))
            continue
        if low in ("?", "??", "unknown", "unsure") or ASK.match(raw):
            q = ASK.match(raw).group(1).strip() if ASK.match(raw) else "yes"
            fresh.append((rid, "cluster", cid, "needs_identifying",
                          q[:1].upper() + q[1:], row_who))
            continue
        if low.startswith("unsure") or low in ("blurry", "unidentifiable"):
            fresh.append((rid, "cluster", cid, "unidentifiable", low, row_who))
            continue
        name, was_folded = canonical(raw, names)
        if was_folded:
            folded.append((raw, name))
        fresh.append((rid, "cluster", cid, "person", name, row_who))
    return fresh, skipped, refused, folded


def _structured(r, rid, who, known, names, allowed):
    """One app row that says what it means. No string guessing: "unknown" in
    a structured row is a value, never a question."""
    scope = str(r.get("scope") or "").strip()
    target = str(r.get("target") or "").strip()
    field = str(r.get("field") or "").strip()
    raw = str(r.get("value") or "").strip()
    key = (scope, field)
    if key not in ALLOWED:
        return ("refused", (rid, target, raw,
                            "{}/{} is not something the app may answer".format(
                                scope, field)), None)
    if not target or not raw:
        return ("refused", (rid, target, raw, "no target or no value"), None)
    if len(raw) > 60:
        return ("refused", (rid, target, raw[:40], "that is a sentence, not a name"), None)
    if scope == "cluster" and target not in known:
        return ("refused", (rid, target, raw, "no such cluster in the tag store"), None)
    if scope == "file":
        if allowed is None:
            return ("refused", (rid, target, raw,
                                "file answers need --allowed (the share set)"), None)
        if target.lower() not in allowed:
            return ("refused", (rid, target, raw,
                                "that photograph is not in the share set"), None)
    if ALLOWED[key] is not None and raw.lower() not in ALLOWED[key]:
        return ("refused", (rid, target, raw,
                            "{!r} is not an allowed {}".format(raw, field)), None)
    if field == "approx_year" and not APPROX_YEAR.match(raw):
        return ("refused", (rid, target, raw,
                            "a year is 1987 or a decade is 1980s"), None)
    value, was = raw, None
    if field == "person":
        value, f = canonical(raw, names)
        was = (raw, value) if f else None
    elif field == "unidentifiable":
        value = raw.lower()
    return ("fresh", (rid, scope, target, field, value, who), was)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True,
                    help="JSON: a list of {id, cluster, name} objects (artifact "
                         "game) or {id, scope, target, field, value, who} (app)")
    ap.add_argument("--store", default=STORE)
    ap.add_argument("--tags", default=TAGS)
    ap.add_argument("--cursor", default=CURSOR)
    ap.add_argument("--who", default="krish",
                    help="whose answers these are when a row does not say - "
                         "every game writes ONE journal, so provenance is not "
                         "optional")
    ap.add_argument("--allowed", default="",
                    help="share-set hashes, one per line; required for file rows")
    ap.add_argument("--status-out", default="",
                    help="write {id: {status, reason}} here for the caller")
    # An argument, never a constant read directly: see answers.BACKUP.
    ap.add_argument("--backup", default=BACKUP,
                    help="off-disk copy of the journal, refreshed on --apply")
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
    names = known_names(Journal(a.store, who=a.who))
    print("clusters in store  : {:,}".format(len(known)))
    print("names already known: {:,}".format(len(names)))

    fresh, skipped, refused, folded = plan(rows, seen, known, names, a.who,
                                           load_allowed(a.allowed))

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
        print("     REFUSED {:<10} {!r:<22} {}".format(cid[:10], raw[:22], why))

    by_field = collections.Counter(f[3] for f in fresh)
    if fresh:
        print("  {}".format(dict(by_field)))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    journals = {}
    for rid, scope, target, field, value, who in fresh:
        j = journals.get(who) or journals.setdefault(who, Journal(a.store, who=who))
        j.record(scope, target, field, value,
                 note="from the {} game".format(who) if scope == "cluster"
                 and not rid.startswith("app-") else "from the archives app")
        if rid:
            seen.add(rid)
    save_cursor(a.cursor, seen)
    if a.status_out:
        status = {rid: {"status": "ingested", "reason": ""}
                  for rid, *_ in fresh if rid}
        status.update({rid: {"status": "refused", "reason": why}
                       for rid, _, _, why in refused if rid})
        with io.open(a.status_out, "w", encoding="utf-8") as fh:
            json.dump(status, fh, indent=1)
    print()
    print("recorded {:,} answers from {}".format(
        len(fresh), ", ".join(sorted(journals)) or "nobody"))
    print("cursor now holds {:,} ingested ids: {}".format(len(seen), a.cursor))
    if fresh:
        backup_journal(Journal(a.store).path, a.backup)
    print("rebuild the index to see them on the photographs:")
    print("    python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
