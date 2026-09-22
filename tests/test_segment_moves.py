r"""Stage 09's first tests: a move that cannot be reversed is not a move.

    python tests\test_segment_moves.py

WHY THESE EXIST NOW

Stage 09 moves files around the library and had NO tests at all - recorded as
debt in its STAGE.md. It is about to move 88 files for the intimate sweep and
18,985 for the segmentation split. That is the wrong moment to inherit the debt.

The two behaviours worth pinning are the ones that are invisible when they
break:

  1. REVERSAL. The journal is written before anything moves, so `--reverse`
     must put every file back where it came from. A move without a reversal is
     a hope.
  2. COLLISION. Two sources can share a basename across different months and
     land on the same destination. Overwriting one photograph with another to
     tidy a folder destroys the thing the project exists to protect.

And the collision branch has never run in anger: the real sweep found 0
collisions in 88 files, so it is exactly the guard nobody has seen fail
(learning 44). It is constructed here on purpose.
"""

import csv
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

import sweep_intimate as S                               # noqa: E402
import apply_split_by_path as A                          # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def fixture(d, pairs):
    r"""A tiny library and an index that says which files are intimate.

    pairs: (relative path, sensitivity, year). Files are created for real, so
    the move is a real move on a real filesystem - a mocked one would prove
    nothing about \\?\ paths or about makedirs.
    """
    lib = os.path.join(d, "ContentLibrary")
    db_path = os.path.join(d, "library.db")
    db = sqlite3.connect(db_path)
    db.executescript("""
        CREATE TABLE files (path TEXT, hash TEXT, year TEXT);
        CREATE TABLE v_files (hash TEXT, sensitivity TEXT, kind TEXT);
    """)
    for i, (rel, sens, year) in enumerate(pairs):
        p = os.path.join(lib, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8").write("photo {}".format(i))
        h = "h{}".format(i)
        db.execute("INSERT INTO files VALUES (?,?,?)", (p, h, year))
        db.execute("INSERT INTO v_files VALUES (?,?,?)", (h, sens, "photo"))
    db.commit()
    db.close()
    return lib, db_path


def main():
    d = tempfile.mkdtemp()
    dest = os.path.join(d, "ContentLibrary", "Media", "Personal", "Intimate")

    print("1. only the intimate files are planned, and the destination is FLAT")
    lib, db_path = fixture(d, [
        (r"Media\Personal\2012\2012-08\a.jpg", "intimate", "2012"),
        (r"Media\Personal\2012\2012-09\b.jpg", "none", "2012"),
        (r"_Review\Media\c.jpg", "intimate", "2019"),
        # DIRECTLY in Intimate, which is what "home" now means. A file in
        # Intimate\<year>\ is NOT home any more - section 6 covers that.
        (r"Media\Personal\Intimate\d.jpg", "intimate", "2020"),
    ])
    rows = S.plan(db_path, dest)
    srcs = sorted(os.path.basename(r["source"]) for r in rows)
    check("the two intimate files outside Intimate are planned",
          srcs, ["a.jpg", "c.jpg"])
    check("a file already in Intimate is left alone",
          any("d.jpg" in r["source"] for r in rows), False)
    check("a non-intimate file is never touched",
          any("b.jpg" in r["source"] for r in rows), False)
    check("_Review is included - Krish overrode that invariant knowingly",
          any(r"_Review" in r["source"] for r in rows), True)
    # The destination used to carry a `<year>\` segment. Krish, 2026-09-18:
    # "lets remove the chronology folder structure from Intimate and just have
    # all the media in that one folder". A year segment here is now a
    # regression, not a feature.
    check("the destination is the folder itself, with no year segment",
          os.path.dirname(
              [r for r in rows if "a.jpg" in r["source"]][0]["destination"]),
          dest)

    print()
    print("2. a real move, then a REVERSAL that puts everything back")
    journal = os.path.join(d, "journal.csv")
    with io.open(journal, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=S.FIELDS)
        w.writeheader()
        w.writerows(rows)
    import shutil
    for r in rows:
        os.makedirs(os.path.dirname(S.lp(r["destination"])), exist_ok=True)
        shutil.move(S.lp(r["source"]), S.lp(r["destination"]))
    check("every planned file has moved",
          [os.path.exists(S.lp(r["source"])) for r in rows], [False, False])
    check("and each is at its destination",
          [os.path.exists(S.lp(r["destination"])) for r in rows], [True, True])
    check("reverse() reports success", S.reverse(journal), 0)
    check("every file is back where it started",
          [os.path.exists(S.lp(r["source"])) for r in rows], [True, True])
    check("and nothing is left at the destination",
          [os.path.exists(S.lp(r["destination"])) for r in rows], [False, False])

    print()
    print("3. reverse REFUSES when the source is occupied again")
    for r in rows:
        shutil.move(S.lp(r["source"]), S.lp(r["destination"]))
    # something has taken the original name back
    io.open(S.lp(rows[0]["source"]), "w", encoding="utf-8").write("different")
    code = S.reverse(journal)
    check("it exits non-zero rather than clobbering", code, 1)
    check("the occupying file is untouched",
          io.open(S.lp(rows[0]["source"]), encoding="utf-8").read(),
          "different")

    print()
    print("4. a destination COLLISION stops the whole run (never seen in anger)")
    d2 = tempfile.mkdtemp()
    dest2 = os.path.join(d2, "ContentLibrary", "Media", "Personal", "Intimate")
    lib2, db2 = fixture(d2, [
        # same basename, different months: both would land on Intimate\2012\x.jpg
        (r"Media\Personal\2012\2012-03\x.jpg", "intimate", "2012"),
        (r"Media\Personal\2012\2012-11\x.jpg", "intimate", "2012"),
    ])
    rows2 = S.plan(db2, dest2)
    dests = [r["destination"] for r in rows2]
    check("two sources really do collide on one destination",
          dests[0] == dests[1], True)
    argv = sys.argv
    try:
        sys.argv = ["sweep_intimate.py", "--db", db2, "--dest", dest2, "--apply",
                    "--journal", os.path.join(d2, "j.csv")]
        code = S.main()
    finally:
        sys.argv = argv
    check("the run STOPS instead of overwriting", code, 1)
    check("both files are still where they were",
          [os.path.exists(S.lp(r["source"])) for r in rows2], [True, True])
    check("and no journal was written", os.path.exists(
        os.path.join(d2, "j.csv")), False)

    print()
    print("5. collisions: duplicates skipped, different photographs renamed")
    # Krish, 2026-09-18, shown 187 collisions in the split - 49 byte-identical
    # duplicates and 138 different photographs sharing a filename: "rename with
    # a suffix". Nothing is deleted and nothing is overwritten.
    #
    # The rename path has never run on real data, so all three outcomes are
    # constructed here: a guard nobody has watched is indistinguishable from no
    # guard (learning 44).
    import apply_split_by_path as A

    d3 = tempfile.mkdtemp()
    src = os.path.join(d3, "src")
    dst = os.path.join(d3, "dst")
    os.makedirs(src, exist_ok=True)
    os.makedirs(dst, exist_ok=True)

    def put(p, text):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8").write(text)
        return p

    # identical content at the destination
    a_src = put(os.path.join(src, "same.jpg"), "identical")
    put(os.path.join(dst, "same.jpg"), "identical")
    # different content, same name
    b_src = put(os.path.join(src, "diff.jpg"), "the source photograph")
    put(os.path.join(dst, "diff.jpg"), "a DIFFERENT photograph")
    # nothing in the way
    c_src = put(os.path.join(src, "free.jpg"), "unobstructed")

    rows = [{"source": a_src, "destination": os.path.join(dst, "same.jpg")},
            {"source": b_src, "destination": os.path.join(dst, "diff.jpg")},
            {"source": c_src, "destination": os.path.join(dst, "free.jpg")}]
    moves, skipped, renamed, unresolved = A.resolve_collisions(rows)
    check("an identical copy is SKIPPED", [r["source"] for r in skipped],
          [a_src])
    check("a different photograph is RENAMED", [r["source"] for r in renamed],
          [b_src])
    check("the rename gets a __2 suffix",
          os.path.basename(renamed[0]["destination"]), "diff__2.jpg")
    check("an unobstructed file moves untouched",
          sorted(os.path.basename(r["destination"]) for r in moves),
          ["diff__2.jpg", "free.jpg"])
    check("nothing is unresolvable here", unresolved, [])
    check("the file already at the destination is untouched",
          io.open(os.path.join(dst, "diff.jpg"), encoding="utf-8").read(),
          "a DIFFERENT photograph")

    # __2 already taken: probe on, never overwrite the fix's own output
    put(os.path.join(dst, "diff__2.jpg"), "an earlier rename")
    _, _, renamed2, _ = A.resolve_collisions([rows[1]])
    check("a taken __2 probes on to __3",
          os.path.basename(renamed2[0]["destination"]), "diff__3.jpg")

    # two sources wanting ONE destination: still refused
    e1 = put(os.path.join(src, "a", "clash.jpg"), "one")
    e2 = put(os.path.join(src, "b", "clash.jpg"), "two")
    target = os.path.join(dst, "clash.jpg")
    _, _, _, un = A.resolve_collisions(
        [{"source": e1, "destination": target},
         {"source": e2, "destination": target}])
    check("two sources for one destination is REFUSED, not renamed",
          len(un), 1)

    print()
    print("6. the FLATTEN: a year subfolder is not home, and is pruned after")
    # Krish, 2026-09-18: "lets remove the chronology folder structure from
    # Intimate and just have all the media in that one folder".
    #
    # There is no --flatten mode. The whole behaviour rests on one comparison
    # in plan(): home is the folder ITSELF, not the tree beneath it. If that
    # ever reverts to `startswith(dest + "\\")`, plan() finds nothing to move
    # and reports success over a folder still full of year folders - a silent
    # no-op, which is the worst possible failure for a mover.
    d4 = tempfile.mkdtemp()
    dest4 = os.path.join(d4, "ContentLibrary", "Media", "Personal", "Intimate")
    _, db4 = fixture(d4, [
        (r"Media\Personal\Intimate\2021\x.jpg", "intimate", "2021"),
        (r"Media\Personal\Intimate\y.jpg", "intimate", "2022"),
    ])
    rows6 = S.plan(db4, dest4)
    check("a file in Intimate\\<year>\\ IS planned",
          sorted(os.path.basename(r["source"]) for r in rows6), ["x.jpg"])
    check("and its destination is the flat folder",
          rows6[0]["destination"], os.path.join(dest4, "x.jpg"))
    check("a file already sitting directly in Intimate is left alone",
          any("y.jpg" in r["source"] for r in rows6), False)

    for r in rows6:
        os.makedirs(os.path.dirname(S.lp(r["destination"])), exist_ok=True)
        shutil.move(S.lp(r["source"]), S.lp(r["destination"]))
    pruned = S.prune_empty(dest4)
    check("the emptied year folder is pruned",
          [os.path.basename(p) for p in pruned], ["2021"])
    check("and the Intimate folder itself survives", os.path.isdir(dest4), True)
    check("both files now sit directly in Intimate",
          sorted(os.listdir(dest4)), ["x.jpg", "y.jpg"])

    # prune_empty must never remove dest, even when dest is itself empty:
    # os.rmdir on the folder the sweep targets would delete the drawer.
    empty = os.path.join(d4, "EmptyIntimate")
    os.makedirs(empty, exist_ok=True)
    check("an EMPTY dest is still never removed",
          (S.prune_empty(empty), os.path.isdir(empty)), ([], True))

    # A PROPOSAL WHOSE SIDE IS SPELLED WRONG IS REFUSED BEFORE ANYTHING MOVES.
    #
    # `verify` compares side_of(path) - "Personal"/"Communal", capitalised -
    # against the proposal's Side column, exactly. On 2026-09-22 a proposal
    # written with lower-case "communal" moved all 11,707 files CORRECTLY,
    # because the destination drives the move, and then reported "11,707 not
    # where expected": a total-failure verdict on a flawless run. The check
    # could not pass, and said so with total confidence (learning 58's shape).
    #
    # Lower-casing the comparison would hide a genuinely unknown side. The
    # refusal belongs at load, when being wrong costs a message rather than a
    # reversal of 11,707 files.
    d5 = tempfile.mkdtemp(prefix="split-side-")
    bad = os.path.join(d5, "bad.csv")
    with io.open(bad, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Source", "Destination", "Side", "Signal"])
        w.writerow([os.path.join(d5, "a.jpg"), os.path.join(d5, "b.jpg"),
                    "communal", "lower case on purpose"])
    try:
        A.load(bad)
        got = "accepted"
    except SystemExit as e:
        got = "refused" if "Side is" in str(e) else "wrong message: {}".format(e)
    check("a lower-case Side is refused at LOAD, before any move", got, "refused")

    good = os.path.join(d5, "good.csv")
    with io.open(good, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Source", "Destination", "Side", "Signal"])
        w.writerow([os.path.join(d5, "a.jpg"), os.path.join(d5, "b.jpg"),
                    "Communal", "the spelling side_of answers with"])
    check("the spelling side_of answers with is accepted",
          [r["side"] for r in A.load(good)], ["Communal"])

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
