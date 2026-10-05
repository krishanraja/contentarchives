r"""What may leave the library machine for the family app. ONE function decides.

    python stages/13_app/share_set.py                 # counts and held-out reasons
    python stages/13_app/share_set.py --write out.txt # the hashes, one per line

WHY THIS IS NARROWER THAN "ALL OF COMMUNAL"

`side_of()` answers whose life a file belongs to, and `Archive\Communal\
01-Identity` is Communal: passports, financial papers and medical letters all
answer "Communal". `audience` is the access control build_db.py derives, and it
reads no `sensitivity` at all, so a `private-family` photograph (a child in the
bath) is `family` because Communal is family by definition. Neither is a
publication rule. This is.

A hash is shared only if EVERY rule holds:

  1. every path that holds it is under \Media\Communal\  - one copy in Archive,
     _Review, Personal or Intimate and the content is NOT shared, because the
     same bytes filed somewhere private were filed there for a reason
  2. it is not in PURGED-HASHES.csv
  3. audience == family
  4. NO SENSITIVE NUDITY. Krish, 2026-10-04: *"it is imperative there is no
     sensitive nudity in this (naked babies or armpits or genuine family moment
     like giving birth is fine, but pictures of my ex girlfriends naked is
     not)"*. So, from the classifier's `sensitivity` and the sensitivity pass's
     raw `nudity` / `subject_age` / `sexual` tags (not in RESOLVED):
       - EMPTY sensitivity is held: never classified is not safe
       - `intimate`, or `sexual = yes`, is never shared
       - nudity (partial/full) is shared ONLY when the subject is a child alone
         and nothing is sexual - the baby in the bath
       - `private-family` is shared only when the nudity pass ran and found
         exactly that; with no verdict it is held, not guessed
       - ANY adult or unclear-age nudity is held, including the genuine family
         moment (a birth) - a machine cannot tell that from what must never be
         shared, so it waits for Krish's own `share = yes` on that one file
     A human `share` answer (written by Krish via the journal; the app's
     whitelist cannot write it) decides either way: `no` hides anything,
     `yes` releases ONLY a nudity hold, never rules 1-3 or 5.
  5. it is a photograph (kind == photo) or a video - never a screenshot,
     document, meme, graphic or poster

Every rule is proven able to fail in tests/test_app_share_set.py: a filter
nobody has seen reject is indistinguishable from no filter (learning 44).
"""

from __future__ import annotations

import argparse
import collections
import io
import os
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from sides import side_of                                        # noqa: E402
from blocklist import blocked_hashes                             # noqa: E402

DB = os.path.join(P.AUDIT, "library.db")
SHARED_ROOT = "\\media\\communal\\"
PRIVATE_MARKS = ("\\intimate\\", "\\archive\\", "\\_review\\", "\\personal\\")


def _norm(p: str) -> str:
    return "\\" + (p or "").replace("/", "\\").lower().lstrip("\\")


def path_ok(path: str) -> bool:
    """Under \\Media\\Communal\\ and nowhere private. Via side_of, never files.side."""
    n = _norm(path)
    return (side_of(path.replace("/", "\\")) == "Communal"
            and SHARED_ROOT in n
            and not any(m in n for m in PRIVATE_MARKS))


def share_set(db: sqlite3.Connection, purged: set, reasons: dict = None):
    """(shared: {hash: {"paths": [...], "media": ...}}, held: Counter of reasons).

    `held` counts each hash once, under the FIRST rule it fails, so the total
    of shared + held is every hash the index knows - nothing disappears
    without a reason being printed.

    `reasons` is an optional dict filled in place with hash -> the SAME reason
    string this function counted, for a caller that must name the held-out
    files rather than only count them (`export_library.py` writes them into
    the export's `held` table, so the cloud never re-judges one). It is an
    out-parameter and not a third return value on purpose: the pair above is
    this function's contract and every existing caller unpacks exactly two.
    Nothing here reads it, so no decision can depend on it.
    """
    paths = collections.defaultdict(list)
    media = {}
    for path, h, m in db.execute(
            "SELECT path, hash, media FROM files "
            "WHERE hash IS NOT NULL AND hash != ''"):
        paths[h].append(path)
        media.setdefault(h, (m or "").lower())

    res = collections.defaultdict(dict)
    for h, field, value in db.execute(
            "SELECT hash, field, value FROM resolved "
            "WHERE field IN ('audience', 'sensitivity', 'kind', 'share')"):
        res[h][field] = (value or "").strip().lower()

    # the sensitivity pass's raw verdict, LATEST per (hash, tag)
    sens = collections.defaultdict(dict)
    for h, tag, value in db.execute(
            "SELECT hash, tag, value FROM tags "
            "WHERE tag IN ('nudity', 'subject_age', 'sexual') "
            "ORDER BY when_, rowid"):
        sens[h][tag] = (value or "").strip().lower()

    shared, held = {}, collections.Counter()
    for h, ps in paths.items():
        r = res.get(h, {})
        if not all(path_ok(p) for p in ps):
            why = "a copy lives outside Media\\Communal"
        elif h.lower() in purged:
            why = "purged"
        elif r.get("audience") != "family":
            why = "audience is not family"
        elif r.get("share") == "no":
            why = "Krish said do not share"
        elif nudity_hold(r.get("sensitivity", ""), sens.get(h, {}),
                         r.get("share") == "yes"):
            why = nudity_hold(r.get("sensitivity", ""), sens.get(h, {}),
                              r.get("share") == "yes")
        elif not (media.get(h) == "video" or r.get("kind") == "photo"):
            why = "not a photograph (" + (r.get("kind") or "no kind") + ")"
        else:
            why = ""
        if why:
            held[why] += 1
            if reasons is not None:
                reasons[h] = why
        else:
            shared[h] = {"paths": sorted(ps), "media": media.get(h) or "photo"}
    return shared, held


def nudity_hold(sensitivity: str, sens: dict, released: bool) -> str:
    """Why this must not be shared, or "" when it may be. See rule 4.

    `released` is Krish's own `share = yes` for this one file. It lifts an
    adult-nudity hold (the birth he named) and nothing else: `intimate` and
    `sexual = yes` stay out whatever anyone answers.
    """
    nudity = sens.get("nudity", "")
    age = sens.get("subject_age", "")
    if sensitivity == "":
        return "never classified for sensitivity"
    if sensitivity == "intimate":
        return "sensitivity is intimate"
    if sens.get("sexual") == "yes":
        return "the nudity pass says sexual"
    if nudity in ("partial", "full"):
        if age == "child":
            return ""                                    # the baby in the bath
        if released:
            return ""
        return "nudity with an adult or unclear age - needs Krish's share=yes"
    if nudity not in ("", "none"):
        return "nudity verdict not understood: " + nudity
    if sensitivity == "private-family":
        if nudity == "none":
            return ""
        return "private-family with no nudity verdict"
    if sensitivity != "none":
        return "sensitivity is " + sensitivity
    return ""


def open_ro(path: str) -> sqlite3.Connection:
    # read-only and closed promptly: build_db renames over this file, and on
    # Windows an open reader makes that rename fail (learning 55)
    return sqlite3.connect("file:{}?mode=ro".format(path.replace("\\", "/")),
                           uri=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--write", default="", help="write the shared hashes here")
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print("STOPPING: no index at {}".format(a.db))
        return 1
    db = open_ro(a.db)
    try:
        shared, held = share_set(db, blocked_hashes())
    finally:
        db.close()
    print("shared   : {:,}".format(len(shared)))
    for why, n in held.most_common():
        print("held out : {:>7,}  {}".format(n, why))
    if a.write:
        with io.open(a.write, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(shared)) + "\n")
        print("wrote {}".format(a.write))
    return 0 if shared else 1


if __name__ == "__main__":
    sys.exit(main())
