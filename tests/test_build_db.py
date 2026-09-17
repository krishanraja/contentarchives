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
    # MIRROR main()'s ORDER, or this helper lies about what a build does.
    # Section 9's four audience checks all returned None and I began diagnosing
    # resolve_audience() - which was correct all along. The step simply was not
    # here: I had added it to build_db.main() and not to the test's private
    # rebuild of the same pipeline, so `resolved` held no audience rows and
    # v_files.audience was NULL for every path.
    B.resolve_audience(db)
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
        print("9. audience: who may SEE this, derived every build")
        # Krish, 2026-09-18: "If I classify a personal photo as someone who also
        # belongs in Communal, it automatically becomes available by others
        # later down the track." So the rule runs continuously and there is no
        # default to decide - an unnamed photograph is not a policy, it is just
        # not named yet.
        #
        # AUDIENCE IS NOT SIDE. Stage 09 holds that a photograph merely
        # CONTAINING Bharti does not belong in Communal. Audience inverts that
        # deliberately: containing her is exactly what she should see. The two
        # rules must never be merged, so both directions are pinned here.
        d2 = tempfile.mkdtemp()
        lib = os.path.join(d2, "Library", "Media")
        inv2 = os.path.join(d2, "INVENTORY.csv")
        f_com = os.path.join(lib, "Communal", "2016", "2016-05", "c.jpg")
        f_both = os.path.join(lib, "Personal", "2016", "2016-05", "p1.jpg")
        f_mine = os.path.join(lib, "Personal", "2016", "2016-05", "p2.jpg")
        f_int = os.path.join(lib, "Personal", "Intimate", "2016", "p3.jpg")
        with io.open(inv2, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["LibraryPath", "Side", "Year", "Month", "Bytes", "Ext",
                        "Kind", "DateTaken", "DateSource", "Make", "Model",
                        "Width", "Height", "Duration", "Lat", "Lon",
                        "OriginFolder", "SourceRoot", "OriginPath"])
            for p in (f_com, f_both, f_mine, f_int):
                w.writerow([p, "Media", "2016", "2016-05", 10, ".jpg", "photo",
                            "", "folder", "", "", "", "", "", "", "", "x", "", ""])
        idx2 = {f_com.lower(): (10, "hc"), f_both.lower(): (10, "hb"),
                f_mine.lower(): (10, "hm"), f_int.lower(): (10, "hi")}
        store2 = os.path.join(d2, "store")
        os.makedirs(store2, exist_ok=True)
        with io.open(os.path.join(store2, "content_tags.csv"), "w",
                     encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["hash", "tag", "value", "source", "confidence", "when"])
            # Mum is in a Communal photograph, so Mum is family
            w.writerow(["hc", "cluster", "c1", "faces", "1.0", "x"])
            w.writerow(["hb", "cluster", "c1", "faces", "1.0", "x"])
            w.writerow(["hi", "cluster", "c1", "faces", "1.0", "x"])
            w.writerow(["hm", "cluster", "c2", "faces", "1.0", "x"])
        j2 = Journal(store2, who="test")
        j2.record("cluster", "c1", "person", "Mum")
        j2.record("cluster", "c2", "person", "Krish")
        db = build(d2, inv2, idx2, store2)
        got = dict(db.execute("SELECT path, audience FROM v_files"))
        check("a Communal photograph is family by definition",
              got.get(f_com), "family")
        check("Personal + someone who appears in Communal is family",
              got.get(f_both), "family")
        check("Personal with only Krish stays private",
              got.get(f_mine), "private")
        check("Personal\\Intimate is private EVEN holding a family member",
              got.get(f_int), "private")
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

        print()
        print("10. a per-path view is never joined on hash")
        # v_files is `FROM files f LEFT JOIN resolved r ... GROUP BY f.path` -
        # one row per PATH, by design, because a path is what the sheets and the
        # movers address. The library holds 82,193 paths against 80,957 hashes:
        # 1,205 hashes have more than one path and one has 26. So joining files
        # back to v_files ON hash matches every path against every other path
        # sharing its hash - the 26-path hash alone contributes 676 rows - and
        # returned 85,281 rows for 82,193 files.
        #
        # Four figures went to Krish off that query as measurements: 3,124 files
        # never examined (2,426), photo 97% / video 93% coverage, and 745
        # private-family files (737 paths, 733 hashes). Nothing errored, and
        # 85,281 looks like a library-sized number. Learning 56.
        d3 = tempfile.mkdtemp()
        try:
            lib3 = os.path.join(d3, "Library", "Media", "Personal",
                                "2016", "2016-08")
            inv3 = os.path.join(d3, "INVENTORY.csv")
            dup_a = os.path.join(lib3, "dup-a.jpg")
            dup_b = os.path.join(lib3, "dup-b.jpg")
            solo = os.path.join(lib3, "solo.jpg")
            with io.open(inv3, "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["LibraryPath", "Side", "Year", "Month", "Bytes",
                            "Ext", "Kind", "DateTaken", "DateSource", "Make",
                            "Model", "Width", "Height", "Duration", "Lat",
                            "Lon", "OriginFolder", "SourceRoot", "OriginPath"])
                for p, b in ((dup_a, 100), (dup_b, 100), (solo, 200)):
                    w.writerow([p, "Personal", "2016", "2016-08", b, ".jpg",
                                "photo", "", "folder", "", "", "", "", "", "",
                                "", "phone", "", ""])
            # dup-a and dup-b are the SAME BYTES under two names: one hash, two
            # paths. This is the ordinary case - 1,236 paths in the real library.
            idx3 = {dup_a.lower(): (100, "hd"), dup_b.lower(): (100, "hd"),
                    solo.lower(): (200, "hs")}
            db = build(d3, inv3, idx3, store)

            n_paths = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            n_hashes = db.execute(
                "SELECT COUNT(DISTINCT hash) FROM files").fetchone()[0]
            check("the fixture has more paths than hashes",
                  (n_paths, n_hashes), (3, 2))
            check("v_files has one row per PATH",
                  db.execute("SELECT COUNT(*) FROM v_files").fetchone()[0],
                  n_paths)

            # The mistake, reproduced: 5 rows out of 3 files.
            joined = db.execute(
                "SELECT COUNT(*) FROM files f "
                "LEFT JOIN v_files v ON v.hash = f.hash").fetchone()[0]
            check("joining on hash INVENTS rows", joined, 5)
            check("and the cheap tell is that it exceeds the file count",
                  joined > n_paths, True)

            # The correct shape for any question about content.
            per_hash = db.execute(
                "SELECT COUNT(*) FROM (SELECT hash, "
                "MAX(COALESCE(sensitivity,'')) FROM v_files GROUP BY hash)"
            ).fetchone()[0]
            check("one row per hash, never one row per join",
                  per_hash, n_hashes)

            # And the same question asked the wrong way, so the gap is visible
            # rather than asserted: counting `none` over the join double-counts
            # the duplicated path.
            by_join = db.execute(
                "SELECT COUNT(*) FROM files f LEFT JOIN v_files v "
                "ON v.hash = f.hash WHERE f.hash = 'hd'").fetchone()[0]
            by_path = db.execute(
                "SELECT COUNT(*) FROM v_files WHERE hash = 'hd'").fetchone()[0]
            check("the duplicated hash is counted 4 times, not 2",
                  (by_join, by_path), (4, 2))
            db.close()
        finally:
            shutil.rmtree(d3, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
