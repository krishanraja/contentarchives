r"""Prove the three things build_db.py could get quietly wrong.

    python tests\test_build_db.py

Not a unit test of every function - a check of the three behaviours that would
be invisible if they broke, on a fixture small enough to reason about:

  1. PRECEDENCE      human beats geonames beats a vision model, per field.
  2. SCOPE EXPANSION one folder answer labels every file under it; one cluster
                     answer labels every photograph that person appears in.
  3. THE INVARIANT   a rebuild never destroys a human answer, because the
                     journal is the source and the database is the copy.

The third is the one worth a test even though it looks obvious. It is the only
data in the project that money and compute cannot reproduce, and a regression
that silently drops it would look exactly like a clean build.
"""

import io
import os
import csv
import sys
import shutil
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_db as B                                  # noqa: E402
from answers import Journal                           # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def fixture(d):
    """Three files: two in one folder sharing a hash-space, one elsewhere."""
    lib = os.path.join(d, "Library", "Media", "Personal")
    inv = os.path.join(d, "INVENTORY.csv")
    f1 = os.path.join(lib, "2016", "2016-08", "a.jpg")
    f2 = os.path.join(lib, "2016", "2016-08", "b.jpg")
    f3 = os.path.join(lib, "2019", "2019-01", "c.jpg")
    with io.open(inv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["LibraryPath", "Side", "Year", "Month", "Bytes", "Ext",
                    "Kind", "DateTaken", "DateSource", "Make", "Model",
                    "Width", "Height", "Duration", "Lat", "Lon",
                    "OriginFolder", "SourceRoot", "OriginPath"])
        w.writerow([f1, "Personal", "2016", "2016-08", 100, ".jpg", "photo",
                    "", "folder", "", "", "", "", "", "", "", "phone", "", ""])
        w.writerow([f2, "Personal", "2016", "2016-08", 200, ".jpg", "photo",
                    "", "folder", "", "", "", "", "", "", "", "phone", "", ""])
        w.writerow([f3, "Personal", "2019", "2019-01", 300, ".jpg", "photo",
                    "", "folder", "", "", "", "", "", "", "", "camera", "", ""])

    # path -> (size, hash), the shape master_sheet.load_hash_index returns
    idx = {f1.lower(): (100, "h1"), f2.lower(): (200, "h2"),
           f3.lower(): (300, "h3")}

    store = os.path.join(d, "store")
    os.makedirs(store, exist_ok=True)
    with io.open(os.path.join(store, "content_tags.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hash", "tag", "value", "source", "confidence", "when"])
        # a model and the geocoder disagree about where h1 is
        w.writerow(["h1", "place", "Paris", "google/gemini-3.1-flash-lite",
                    "0.9", "2026-01-01"])
        w.writerow(["h1", "place", "Edinburgh", "geonames", "1.0", "2026-01-02"])
        w.writerow(["h1", "subject", "a beach at sunset", "geonames", "1.0", "x"])
        # h2 has only a model opinion
        w.writerow(["h2", "place", "Rome", "google/gemini-3.1-flash-lite",
                    "0.9", "2026-01-01"])
        # h3 is in a face cluster
        w.writerow(["h3", "cluster", "c17", "faces", "1.0", "2026-01-01"])
    return inv, idx, store, (f1, f2, f3)


def build(d, inv, idx, store):
    out = os.path.join(d, "library.db")
    if os.path.exists(out):
        os.remove(out)
    db = B.connect(out)
    B.schema(db)
    B.load_files(db, inv, idx)
    B.load_tags(db, store)
    B.resolve(db)
    B.load_answers(db, store)
    B.apply_answers(db)
    B.build_views(db)
    db.commit()
    return db


def main():
    d = tempfile.mkdtemp()
    try:
        inv, idx, store, (f1, f2, f3) = fixture(d)
        folder = os.path.join(d, "Library", "Media", "Personal", "2016")

        print("1. precedence")
        db = build(d, inv, idx, store)
        got = db.execute(
            "SELECT place FROM v_files WHERE path=?", (f1,)).fetchone()[0]
        check("geonames beats the vision model", got, "Edinburgh")
        got = db.execute(
            "SELECT place FROM v_files WHERE path=?", (f2,)).fetchone()[0]
        check("a lone model opinion still shows", got, "Rome")
        n = db.execute("SELECT COUNT(*) FROM tags WHERE hash='h1' "
                       "AND tag='place'").fetchone()[0]
        check("every opinion is kept underneath", n, 2)
        db.close()

        print()
        print("2. scope expansion")
        j = Journal(store, who="test")
        j.record("folder", folder, "event", "Italy")
        j.record("cluster", "c17", "person", "Mum")
        j.record("file", "h1", "place", "Leith")
        db = build(d, inv, idx, store)
        got = [r[0] for r in db.execute(
            "SELECT event FROM v_files WHERE path IN (?,?,?) ORDER BY path",
            (f1, f2, f3))]
        check("one folder answer labels both files under it",
              got, ["Italy", "Italy", None])
        got = db.execute(
            "SELECT person FROM v_files WHERE path=?", (f3,)).fetchone()[0]
        check("one cluster answer labels the photo that person is in",
              got, "Mum")
        got = db.execute(
            "SELECT place FROM v_files WHERE path=?", (f1,)).fetchone()[0]
        check("a human answer beats geonames", got, "Leith")
        db.close()

        print()
        print("3. the invariant: a rebuild cannot destroy an answer")
        journal_before = io.open(os.path.join(store, "answers.csv"),
                                 encoding="utf-8").read()
        for _ in range(3):
            db = build(d, inv, idx, store)
            db.close()
        journal_after = io.open(os.path.join(store, "answers.csv"),
                                encoding="utf-8").read()
        check("three rebuilds left the journal byte-identical",
              journal_after, journal_before)
        db = build(d, inv, idx, store)
        check("answers still in the database after rebuilding",
              db.execute("SELECT COUNT(*) FROM answers").fetchone()[0], 3)
        # the real test: destroy the database, keep the journal
        db.close()
        os.remove(os.path.join(d, "library.db"))
        db = build(d, inv, idx, store)
        got = db.execute(
            "SELECT person FROM v_files WHERE path=?", (f3,)).fetchone()[0]
        check("deleting the database loses nothing a human said", got, "Mum")
        db.close()

        print()
        print("4. full-text search")
        db = build(d, inv, idx, store)
        n = db.execute("SELECT COUNT(*) FROM search WHERE search MATCH ?",
                       ("beach",)).fetchone()[0]
        check("fts finds a word from the subject sentence", n, 1)
        n = db.execute("SELECT COUNT(*) FROM search WHERE search MATCH ?",
                       ("Mum",)).fetchone()[0]
        check("fts finds a person a human named", n, 1)
        db.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
