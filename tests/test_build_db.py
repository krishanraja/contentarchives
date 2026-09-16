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
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever it lives

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
        # ...and a second face in the same photograph, in another cluster
        w.writerow(["h3", "cluster", "c18", "faces", "1.0", "2026-01-01"])
        # A PERSON TAG WITH NO CLUSTER BEHIND IT, written per photograph by an
        # earlier enrichment pass. This is the layer that kept a dead name
        # alive: section 8 renames the cluster and this tag must not resurrect
        # the old one. h2 has the tag and no cluster at all, so it also proves
        # the fix does not strip a name that is a photograph's only one.
        w.writerow(["h3", "person", "Mum", "google/gemini-3.1-flash-lite",
                    "0.9", "2026-01-01"])
        w.writerow(["h2", "person", "Nanna", "google/gemini-3.1-flash-lite",
                    "0.9", "2026-01-01"])
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
    B.resolve_people(db)
    B.build_views(db)
    db.commit()
    return db


def promote_checks(d):
    r"""promote() retries a held target, and refuses LOUDLY without losing work.

    Learning 55: a 19-minute rebuild wrote every row and then died on
    `os.replace(tmp, library.db)` with WinError 5, because a reader still held
    the live database open. The finished database was intact at .tmp the whole
    time. So the three things worth pinning are the swap itself, the retry, and
    above all the message: a traceback on the last line of a long job reads as
    "the work is gone" when the work is right there.

    The lock here is a real one - an open handle on the target - not a mock.
    """
    import threading

    work = os.path.join(d, "promote")
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "library.db")
    tmp = out + ".tmp"

    def fresh(new_bytes=b"new"):
        io.open(out, "wb").write(b"old")
        io.open(tmp, "wb").write(new_bytes)

    # --- a clean swap ------------------------------------------------------
    fresh(b"finished index")
    B.promote(tmp, out)
    check("a clean swap replaces the target", io.open(out, "rb").read(),
          b"finished index")
    check("and the tmp file is gone", os.path.exists(tmp), False)

    # --- a transient lock: retried, then succeeds ---------------------------
    # Windows refuses the rename while this handle is open. It is released from
    # a timer, so the retry loop has to actually wait and try again.
    fresh(b"second index")
    handle = io.open(out, "r+b")
    threading.Timer(3.0, handle.close).start()
    try:
        B.promote(tmp, out)
        swapped = io.open(out, "rb").read()
    finally:
        if not handle.closed:
            handle.close()
    check("a transient lock is retried, not fatal", swapped, b"second index")

    # --- a lock that never lets go: SystemExit, and the work is named -------
    fresh(b"third index")
    handle = io.open(out, "r+b")
    try:
        B.promote(tmp, out, tries=2)
        raised = None
    except SystemExit as e:
        raised = str(e)
    finally:
        handle.close()
    check("a permanent lock stops the run", raised is not None, True)
    said = (raised or "")
    check("it says nothing is lost", "NOTHING IS LOST" in said, True)
    check("it names where the finished database is", tmp in said, True)
    check("and the finished database really is still there",
          os.path.exists(tmp) and io.open(tmp, "rb").read() == b"third index",
          True)
    check("the live file was left untouched", io.open(out, "rb").read(), b"old")


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

        print()
        print("5. a group photograph keeps everybody in it")
        j.record("cluster", "c18", "person", "Dad")
        db = build(d, inv, idx, store)
        got = db.execute(
            "SELECT person FROM v_files WHERE path=?", (f3,)).fetchone()[0]
        check("two named clusters in one photo: both names show",
              got, "Dad; Mum")
        got = [r[0] for r in db.execute(
            "SELECT person FROM photo_people WHERE hash='h3' ORDER BY person")]
        check("photo_people holds a row per person", got, ["Dad", "Mum"])
        db.close()
        j.record("cluster", "c17", "person", "Mother")
        db = build(d, inv, idx, store)
        got = db.execute(
            "SELECT person FROM v_files WHERE path=?", (f3,)).fetchone()[0]
        check("a renamed cluster replaces its old name, not adds to it",
              got, "Dad; Mother")
        db.close()

        print()
        print("8. a name a later answer REPLACED never comes back via the tags")
        # THE RISHI BUG, 2026-09-16. Krish split one "Rishi" into three people.
        # Every cluster was renamed correctly and the index STILL showed a person
        # called "Rishi" on 97 photographs, because `tags` carries person rows
        # written per photograph by an earlier pass, with no cluster behind them,
        # and nothing a human answers can supersede one.
        #
        # Section 5 above passes either way: it renames a cluster and reads
        # `resolved`, and c17/c18 have no tag-layer name. This is the case that
        # engages - "Mum" is BOTH a tag on h3 and a cluster answer that has since
        # become "Mother" - and it fails loudly against the old code.
        db = build(d, inv, idx, store)
        got = [r[0] for r in db.execute(
            "SELECT person FROM photo_people WHERE hash='h3' ORDER BY person")]
        check("the replaced name is gone from photo_people", got,
              ["Dad", "Mother"])
        check("and gone from the joined field too",
              db.execute("SELECT person FROM v_files WHERE path=?",
                         (f3,)).fetchone()[0], "Dad; Mother")
        n = db.execute("SELECT COUNT(*) FROM tags WHERE tag='person' "
                       "AND value='Mum'").fetchone()[0]
        check("but `tags` is untouched - the record of what that pass said", n, 1)
        # The other half: a tag-layer name nobody has contradicted STAYS. 2,107
        # real photographs have no human-sourced name at all, and a fix that
        # dropped the whole layer would silently un-name every one of them.
        got = db.execute("SELECT person FROM v_files WHERE path=?",
                         (f2,)).fetchone()[0]
        check("an uncontradicted tag name still names its photograph",
              got, "Nanna")
        db.close()

        print()
        print("6. the swap survives a lock, and never reports lost work")
        promote_checks(d)

        print()
        print("7. photo_people is indexed on BOTH the columns it is questioned by")
        # person: "which photographs is Bharti in". hash: "which photographs have
        # two or more named people" - that one groups by hash, scanned all 42,693
        # rows without an index, and took over two minutes. chain_rounds.ps1's
        # -Verify joins photo_people.hash to tags.hash at every checkpoint, so
        # the supervision itself pays for a missing index here.
        db = build(d, inv, idx, store)
        idxs = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='photo_people'")}
        check("indexed on person", "photo_people_person" in idxs, True)
        check("indexed on hash", "photo_people_hash" in idxs, True)
        # And prove the group-photograph question uses one, rather than scanning.
        plan = " ".join(str(c) for r in db.execute(
            "EXPLAIN QUERY PLAN SELECT hash FROM photo_people "
            "GROUP BY hash HAVING COUNT(DISTINCT person) > 1") for c in r)
        check("the group-shot query uses an index, not a full scan",
              "photo_people_hash" in plan, True)
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
