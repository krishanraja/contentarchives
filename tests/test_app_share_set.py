r"""Nothing private reaches the family app. Every rule is watched REFUSING.

    python tests\test_app_share_set.py

stages/13_app/share_set.py is the one function that decides what may leave the
library machine for archives.krishraja.com. Each fixture below is built to
break exactly one rule, and the test fails unless that file is held out - a
filter nobody has seen reject is indistinguishable from no filter (learning
44). Krish, 2026-10-04: *"it is imperative there is no sensitive nudity in
this (naked babies or armpits or genuine family moment like giving birth is
fine, but pictures of my ex girlfriends naked is not)"*.
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import stagepath  # noqa: E402,F401

import share_set as S                                            # noqa: E402

FAILURES = []
C = r"D:\ContentLibrary\Media\Communal\2014"


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def h(n):
    return "{:064x}".format(n)


# name -> (paths, resolved, raw sensitivity tags, should it be shared?)
CASES = {
    "an ordinary Communal photograph": (
        [C + r"\a.jpg"], {}, {}, True),
    "a Communal video": (
        [C + r"\v.mp4"], {"kind": "photo"}, {}, True),
    "an identity document in Archive\\Communal": (
        [r"D:\ContentLibrary\Archive\Communal\01-Identity\p.jpg"], {}, {}, False),
    "a Communal file still in _Review": (
        [r"D:\ContentLibrary\_Review\Communal\r.jpg"], {}, {}, False),
    "a Personal photograph": (
        [r"D:\ContentLibrary\Media\Personal\2014\x.jpg"], {}, {}, False),
    "the same bytes also filed in Intimate": (
        [C + r"\i.jpg", r"D:\ContentLibrary\Media\Personal\Intimate\i.jpg"],
        {}, {}, False),
    "a purged hash": ([C + r"\purged.jpg"], {}, {}, False),
    "audience private": ([C + r"\pr.jpg"], {"audience": "private"}, {}, False),
    "never classified for sensitivity": (
        [C + r"\nc.jpg"], {"sensitivity": ""}, {}, False),
    "sensitivity intimate": (
        [C + r"\in.jpg"], {"sensitivity": "intimate"}, {}, False),
    "an ADULT naked - the case that must never ship": (
        [C + r"\ad.jpg"], {"sensitivity": "none"},
        {"nudity": "full", "subject_age": "adult", "sexual": "no"}, False),
    "partial nudity, age unclear": (
        [C + r"\un.jpg"], {"sensitivity": "none"},
        {"nudity": "partial", "subject_age": "unclear", "sexual": "no"}, False),
    "adults AND a child naked": (
        [C + r"\bo.jpg"], {"sensitivity": "private-family"},
        {"nudity": "partial", "subject_age": "both", "sexual": "no"}, False),
    "anything sexual, even with Krish's share=yes": (
        [C + r"\sx.jpg"], {"sensitivity": "none", "share": "yes"},
        {"nudity": "full", "subject_age": "adult", "sexual": "yes"}, False),
    "the baby in the bath (child alone, not sexual)": (
        [C + r"\bath.jpg"], {"sensitivity": "private-family"},
        {"nudity": "full", "subject_age": "child", "sexual": "no"}, True),
    "private-family with no nudity verdict at all": (
        [C + r"\pf.jpg"], {"sensitivity": "private-family"}, {}, False),
    "a birth, released by Krish's own share=yes": (
        [C + r"\birth.jpg"], {"sensitivity": "none", "share": "yes"},
        {"nudity": "partial", "subject_age": "adult", "sexual": "no"}, True),
    "Krish's share=no hides an ordinary photo": (
        [C + r"\no.jpg"], {"share": "no"}, {}, False),
    "a screenshot": ([C + r"\s.png"], {"kind": "screenshot"}, {}, False),
    "a document": ([C + r"\d.jpg"], {"kind": "document"}, {}, False),
}


def build():
    db = sqlite3.connect(":memory:")
    db.executescript("""
      CREATE TABLE files (path TEXT, hash TEXT, media TEXT);
      CREATE TABLE tags (hash TEXT, tag TEXT, value TEXT, source TEXT,
                         confidence REAL, when_ TEXT);
      CREATE TABLE resolved (hash TEXT, field TEXT, value TEXT, source TEXT,
                             confidence REAL);
    """)
    ids = {}
    for n, (name, (paths, res, sens, _)) in enumerate(CASES.items()):
        hh = h(n + 1)
        ids[name] = hh
        for p in paths:
            db.execute("INSERT INTO files VALUES (?,?,?)",
                       (p, hh, "video" if p.endswith(".mp4") else "photo"))
        base = {"audience": "family", "sensitivity": "none", "kind": "photo"}
        base.update(res)
        for f, v in base.items():
            db.execute("INSERT INTO resolved VALUES (?,?,?,?,?)",
                       (hh, f, v, "x", 1.0))
        for t, v in sens.items():
            db.execute("INSERT INTO tags VALUES (?,?,?,?,?,?)",
                       (hh, t, v, "sens", 1.0, "2026"))
    return db, ids


def main():
    db, ids = build()
    shared, held = S.share_set(db, {ids["a purged hash"]})
    print("each fixture is shared or held exactly as rule 1-5 says:")
    for name, (_, _, _, want) in CASES.items():
        check(name, ids[name] in shared, want)

    print()
    print("nothing disappears without a reason")
    check("shared + held accounts for every hash",
          len(shared) + sum(held.values()), len(CASES))

    print()
    print("a LATER nudity verdict wins over an earlier one")
    db.execute("INSERT INTO tags VALUES (?,?,?,?,?,?)",
               (ids["an ordinary Communal photograph"], "nudity", "full",
                "sens", 1.0, "2027"))
    db.execute("INSERT INTO tags VALUES (?,?,?,?,?,?)",
               (ids["an ordinary Communal photograph"], "subject_age", "adult",
                "sens", 1.0, "2027"))
    shared, _ = S.share_set(db, set())
    check("a photo re-judged as adult nudity is withdrawn",
          ids["an ordinary Communal photograph"] in shared, False)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
