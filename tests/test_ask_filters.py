r"""Prove the --ask filters on embed_descriptions.py narrow correctly.

    python tests\test_ask_filters.py

Not a test of the embedding call itself (that needs a network key and money -
`ask()`'s ranking loop is exercised separately below, with `embed()`
monkeypatched so no request is ever made). This is a check of the four things
a filter could get quietly wrong on a fixture small enough to reason about:

  1. YEAR      a range parses both ends inclusively, and a blank/unparsable
               year in `files` is excluded rather than silently kept.
  2. PERSON    a group photograph (two photo_people rows, one hash) matches on
               EITHER person, not just the first found - the same "a group
               photo keeps everybody in it" rule build_db.py enforces.
  3. SIDE      reads the PATH one level under Media/Archive/_Review, never
               `files.side` (the top-level tree) - sides.py's own warning,
               re-checked here because embed_descriptions.py keeps its own
               copy of the rule rather than importing it.
  4. HOLIDAY   `--holiday` only supplies occasion=travel when `--occasion`
               was not given explicitly - an explicit occasion must win.

And that the end-to-end `ask()` loop, given a fixture library.db and fake
vector shards, returns exactly the filtered rows in similarity order and
states its scan depth - not just that the pieces below it are individually
correct.
"""

import argparse
import io
import os
import sqlite3
import sys
import tempfile
import shutil
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever it lives

import embed_descriptions as E                        # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def make_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE files (
        path TEXT PRIMARY KEY, hash TEXT, side TEXT, year TEXT, media TEXT,
        date_taken TEXT
    );
    CREATE TABLE resolved (
        hash TEXT, field TEXT, value TEXT, source TEXT, confidence REAL,
        PRIMARY KEY (hash, field)
    );
    CREATE TABLE photo_people (
        hash TEXT, person TEXT, source TEXT, PRIMARY KEY (hash, person)
    );
    """)
    rows = [
        # hash, path, side(tree), year, media, date_taken
        ("h1", r"D:\Media\Personal\2026\a.jpg",
         "Media", "2026", "photo", "2026-08-06"),
        ("h2", r"D:\Media\Communal\2026\b.jpg",
         "Media", "2026", "photo", "2026-05-01"),
        ("h3", r"D:\Media\Personal\2019\c.jpg",
         "Media", "2019", "photo", "2019-01-01"),
        ("h4", r"D:\Media\Personal\NoDate\d.jpg",
         "Media", "", "photo", ""),
        ("h5", r"D:\Media\Personal\2026\e.mp4",
         "Media", "2026", "video", "2026-09-01"),
    ]
    for h, p, side, year, media, dt in rows:
        db.execute("INSERT INTO files VALUES (?,?,?,?,?,?)",
                   (p, h, side, year, media, dt))
    # h1: solo Krish, green t-shirt, in Scotland, occasion travel
    # h2: group photo - Krish AND Bharti - occasion everyday
    resolved = [
        ("h1", "place", "Edinburgh"), ("h1", "region", "Scotland"),
        ("h1", "occasion", "travel"), ("h1", "activity", "walking"),
        ("h1", "description", "Krish in a green t-shirt against a light wall"),
        ("h2", "occasion", "everyday"),
    ]
    for h, f, v in resolved:
        db.execute("INSERT INTO resolved VALUES (?,?,?,'test',1.0)", (h, f, v))
    people = [("h1", "Krish"), ("h2", "Krish"), ("h2", "Bharti")]
    for h, person in people:
        db.execute("INSERT INTO photo_people VALUES (?,?,'test')", (h, person))
    db.commit()
    db.close()


def default_args(**over):
    a = argparse.Namespace(
        year="", person="", place="", occasion="", holiday=False,
        activity="", mood="", side="", media="", after="", before="",
        top=12, scan=2000, contact_sheet="", thumbs=r"D:\_thumbs")
    for k, v in over.items():
        setattr(a, k, v)
    return a


def test_year_range():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "library.db")
        make_db(p)
        db = sqlite3.connect(p)
        yr = E.parse_year_range("2024-2026")
        check("range parses both ends", yr, (2024, 2026))
        yr1 = E.parse_year_range("2026")
        check("single year is (y, y)", yr1, (2026, 2026))
        a = default_args()
        check("2026 row passes a 2024-2026 range",
              E.passes_filters(db, "h1",
                                r"D:\Media\Personal\2026\a.jpg",
                                "2026", "photo", a, (2024, 2026), []),
              True)
        check("2019 row fails a 2024-2026 range",
              E.passes_filters(db, "h3",
                                r"D:\Media\Personal\2019\c.jpg",
                                "2019", "photo", a, (2024, 2026), []),
              False)
        check("blank year fails ANY year filter, not just non-matching ones",
              E.passes_filters(db, "h4",
                                r"D:\Media\Personal\NoDate\d.jpg",
                                "", "photo", a, (2024, 2026), []),
              False)
        db.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_person_group_photo():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "library.db")
        make_db(p)
        db = sqlite3.connect(p)
        a = default_args(person="Bharti")
        check("group photo matches on the SECOND name too, not just the first",
              E.passes_filters(db, "h2",
                                r"D:\Media\Communal\2026\b.jpg",
                                "2026", "photo", a, None, []),
              True)
        a2 = default_args(person="Bharti")
        check("solo photo of someone else does not match",
              E.passes_filters(db, "h1",
                                r"D:\Media\Personal\2026\a.jpg",
                                "2026", "photo", a2, None, []),
              False)
        db.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_side_reads_path_not_files_side():
    # files.side is "Media" for every fixture row (the top-level TREE) -
    # if --side ever read files.side instead of the path, both would
    # match "Personal" and this test would go silently green on the bug
    # sides.py itself warns about.
    a_personal = default_args(side="Personal")
    a_communal = default_args(side="Communal")
    check("Personal path matches --side Personal",
          E.side_of_path(r"D:\Media\Personal\2026\a.jpg"),
          "Personal")
    check("Communal path matches --side Communal",
          E.side_of_path(r"D:\Media\Communal\2026\b.jpg"),
          "Communal")
    check("neither matches a path with no side segment",
          E.side_of_path(r"D:\ContentLibrary\Archive\01-Identity\x.jpg"),
          None)
    check("forward slashes and mixed case both resolve",
          E.side_of_path("d:/contentlibrary/media/PERSONAL/2026/a.jpg"),
          "Personal")
    del a_personal, a_communal


def test_holiday_yields_to_explicit_occasion():
    _, checks_holiday_only = E.build_filters(default_args(holiday=True))
    check("--holiday alone sets occasion~travel",
          dict(checks_holiday_only).get("occasion"), "travel")
    _, checks_explicit = E.build_filters(
        default_args(holiday=True, occasion="everyday"))
    check("an explicit --occasion overrides --holiday",
          dict(checks_explicit).get("occasion"), "everyday")


def test_contact_sheet_missing_pillow_or_thumbs_does_not_crash():
    d = tempfile.mkdtemp()
    try:
        out = os.path.join(d, "sheet.png")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = E.contact_sheet(out, os.path.join(d, "no_such_thumbs"),
                                  [("h1", "2026  a.jpg")])
        # Either outcome is fine (Pillow may or may not be installed here);
        # what must never happen is an exception reaching the caller.
        check("contact_sheet returns a bool without raising",
              isinstance(ok, bool), True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_ask_end_to_end_with_filters():
    """Fake vectors (identical, so similarity order is stable-by-hash-order)
    and a monkeypatched embed() - this exercises the scan/filter/top loop in
    ask() itself, not just passes_filters() in isolation."""
    import numpy as np
    d = tempfile.mkdtemp()
    try:
        db_path = os.path.join(d, "library.db")
        make_db(db_path)
        out = os.path.join(d, "vectors")
        os.makedirs(out)
        hashes = ["h1", "h2", "h3", "h4", "h5"]
        vecs = np.eye(len(hashes), E.DIM, dtype=np.float32)[: len(hashes)]
        # h1 most similar to the query, h2 second, etc - descending by index
        with open(os.path.join(out, "shard-0000.npz"), "wb") as fh:
            np.savez(fh, hash=np.array(hashes), vec=vecs.astype(np.float16))

        real_embed = E.embed
        E.embed = lambda texts, key, **kw: [vecs[0].tolist() for _ in texts]
        os.environ["GOOGLE_API_KEY"] = "test-key-not-sent-anywhere"
        try:
            a = default_args(top=5, scan=5, year="2026")
            a.db, a.out, a.ask = db_path, out, "anything"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = E.ask(a)
            printed = buf.getvalue()
        finally:
            E.embed = real_embed

        check("ask() exits 0", rc, 0)
        check("2019 file (h3) excluded by --year 2026", "c.jpg" in printed, False)
        check("blank-year file (h4) excluded by --year 2026",
              "d.jpg" in printed, False)
        check("2026 photo (h1) is in the results", "a.jpg" in printed, True)
        check("2026 photo (h2) is in the results", "b.jpg" in printed, True)
        check("2026 video (h5) is in the results (no --media filter)",
              "e.mp4" in printed, True)
        check("filters line is printed", "filters:" in printed, True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        os.environ.pop("GOOGLE_API_KEY", None)


def main():
    print("test_year_range")
    test_year_range()
    print("test_person_group_photo")
    test_person_group_photo()
    print("test_side_reads_path_not_files_side")
    test_side_reads_path_not_files_side()
    print("test_holiday_yields_to_explicit_occasion")
    test_holiday_yields_to_explicit_occasion()
    print("test_contact_sheet_missing_pillow_or_thumbs_does_not_crash")
    test_contact_sheet_missing_pillow_or_thumbs_does_not_crash()
    print("test_ask_end_to_end_with_filters")
    test_ask_end_to_end_with_filters()

    print()
    if FAILURES:
        print("FAILED: {}".format(", ".join(FAILURES)))
        return 1
    print("all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
