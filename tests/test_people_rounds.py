r"""A face Krish refused must never be shown to him again.

    python tests\test_people_rounds.py

WHY

Krish, 2026-09-16: "Stop resending me batches I have refused to identify - they
are unidentifiable." He was right and the cause was structural: people_sheet.py
hides a row only when the answers journal holds something about it, and a row
left blank - or skipped with the dash button - reached the journal as nothing at
all. record_people.py dropped `c123 = -` on the floor. Measured when he said it:
186 rows shown across four sheets, 60 never answered, so each new sheet
re-offered faces he had already passed over, twice in some cases.

A refusal is an answer. These checks watch that hold, and watch it fail if the
recording is skipped - a fix believed without a test is how the original bug
survived four rounds.
"""

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

RECORD = os.path.join(ROOT, "stages", "07_people", "record_people.py")
FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def run(*args, store=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, RECORD] + list(args), capture_output=True,
                       text=True, env=env, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def fixture(d):
    """A store with three known clusters, and a sheet showing all three."""
    store = os.path.join(d, "store")
    os.makedirs(store)
    with io.open(os.path.join(store, "content_tags.csv"), "w", encoding="utf-8",
                 newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "tag", "value", "source", "confidence", "when"])
        for cid in ("c1", "c2", "c3"):
            for i in range(3):
                w.writerow(["h{}{}".format(cid, i), "cluster", cid, "faces", "1.0", "x"])
    sheet = os.path.join(d, "PEOPLE.html")
    io.open(sheet, "w", encoding="utf-8").write(
        "".join('<div class="row" data-cid="{}" data-photos="5"></div>'.format(c)
                for c in ("c1", "c2", "c3")))
    return store, sheet


def answers_of(store):
    p = os.path.join(store, "answers.csv")
    if not os.path.exists(p):
        return []
    return list(csv.DictReader(io.open(p, encoding="utf-8", newline="")))


def sheet_of(path, cids):
    """A naming sheet showing exactly these cluster rows."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8").write(
        "".join('<div class="row" data-cid="{}" data-photos="5"></div>'.format(c)
                for c in cids))
    return path


def test_repeat_guard(d):
    r"""No sheet re-shows a row already offered - over EVERY round.

    check_repeats.py matched `PEOPLE-round[1-6].html` until 2026-09-16. It was
    written when round 7 was the next sheet and never widened, so rounds 7, 8
    and 9 were invisible to it: its baseline sat frozen at 186 rows for three
    consecutive runs while each new sheet was reported clean. Rounds 7-10 were
    genuinely clean, so the verdicts held - by luck, not by test (learning 55).

    So the regression check that matters is the one on round SEVEN, and the
    guard has to be watched catching a repeat as well as passing a clean sheet:
    a guard nobody has seen fail is indistinguishable from one that cannot fail
    (learning 44).
    """
    import check_repeats as C

    os.makedirs(d, exist_ok=True)
    sheet_of(os.path.join(d, "PEOPLE-round1.html"), ["c1", "c2"])
    sheet_of(os.path.join(d, "PEOPLE-round7.html"), ["c7", "c8"])
    # Fixtures that live beside real sheets must not join the baseline.
    sheet_of(os.path.join(d, "PEOPLE-tampered.html"), ["c99"])

    clean = sheet_of(os.path.join(d, "PEOPLE-round8.html"), ["c20", "c21"])
    dup, rows, seen, sources = C.repeats(d, clean)
    check("a sheet of new rows is clean", dup, [])
    check("it read both earlier rounds", sorted(sources),
          ["PEOPLE-round1.html", "PEOPLE-round7.html"])
    check("the fixture is not in the baseline", "c99" in seen, False)
    check("main() exits 0 on a clean sheet", C.main([d, clean]), 0)

    # A row from round 1 coming back: the original defect.
    again = sheet_of(os.path.join(d, "PEOPLE-round9.html"), ["c1", "c30"])
    dup, rows, seen, sources = C.repeats(d, again)
    check("a repeat from round 1 is CAUGHT", dup, ["c1"])
    check("main() exits 1 on a repeat", C.main([d, again]), 1)

    # THE REGRESSION: a row from round 7, which the old [1-6] pattern missed.
    seven = sheet_of(os.path.join(d, "PEOPLE-round10.html"), ["c7", "c31"])
    dup, rows, seen, sources = C.repeats(d, seven)
    check("a repeat from round SEVEN is caught (the [1-6] scar)", dup, ["c7"])

    # A merged cluster: same person, new id, still a repeat.
    merges = os.path.join(d, "CLUSTER-MERGES.csv")
    with io.open(merges, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cluster", "group"])
        w.writerow(["c1", "g1"])
        w.writerow(["c500", "g1"])
    merged = sheet_of(os.path.join(d, "PEOPLE-round11.html"), ["c500"])
    dup, rows, seen, sources = C.repeats(d, merged, merges=merges)
    check("the same person under a new cluster id is still a repeat", dup, ["g1"])

    # The sheet under test never counts as its own history.
    solo = sheet_of(os.path.join(d, "PEOPLE-round12.html"), ["c77"])
    dup, rows, seen, sources = C.repeats(d, solo)
    check("a sheet is not its own baseline", "c77" in seen, False)


def main():
    d = tempfile.mkdtemp()
    try:
        store, sheet = fixture(d)
        tags = os.path.join(store, "content_tags.csv")

        print("1. a row named, a row skipped, a row left blank")
        code, out = run("--from-text", "c1 = Mum\nc2 = -", "--store", store,
                        "--tags", tags, "--sheet", sheet, "--apply")
        check("it records", code, 0)
        rows = {r["target"]: (r["field"], r["value"]) for r in answers_of(store)}
        check("the named row is a person", rows.get("c1"), ("person", "Mum"))
        check("the SKIPPED row is recorded, not dropped", rows.get("c2"),
              ("unidentifiable", "declined"))
        check("the BLANK row is recorded as declined", rows.get("c3"),
              ("unidentifiable", "declined"))
        notes = {r["target"]: r["note"] for r in answers_of(store)}
        check("and says which way it was refused", notes.get("c3"), "shown and not named")

        print()
        print("2. the sheet generator now has something to skip")
        # people_sheet treats person, needs_identifying and unidentifiable as
        # answered; every row above is one of those, so the next sheet has none
        answered = {r["target"] for r in answers_of(store)
                    if r["field"] in ("person", "needs_identifying", "unidentifiable")}
        check("all three rows count as answered", sorted(answered), ["c1", "c2", "c3"])

        print()
        print("3. without --sheet, a blank row is invisible (the original bug)")
        store2, sheet2 = fixture(os.path.join(d, "b"))
        os.makedirs(os.path.dirname(sheet2), exist_ok=True)
        code, out = run("--from-text", "c1 = Mum", "--store", store2,
                        "--tags", os.path.join(store2, "content_tags.csv"), "--apply")
        rows2 = {r["target"] for r in answers_of(store2)}
        check("only the named row is recorded", sorted(rows2), ["c1"])
        check("so c2 and c3 would be shown again", "c3" in rows2, False)

        print()
        print("4. a paste that carries prose (2026-09-16)")
        store3, _ = fixture(os.path.join(d, "prose"))
        tags3 = os.path.join(store3, "content_tags.csv")
        code, out = run("--from-text",
                        "c1 = Krish. Agree with your recommendation on no2, and i think "
                        "one off investigations need to be stored\nc2 = Mum",
                        "--store", store3, "--tags", tags3, "--apply")
        rows3 = {r["target"]: (r["field"], r["value"], r["note"]) for r in answers_of(store3)}
        check("the name ends at the sentence break", rows3.get("c1", ("", "", ""))[:2],
              ("person", "Krish"))
        check("and the rest is kept as a note",
              rows3.get("c1", ("", "", ""))[2].startswith("Agree with your recommendation"), True)
        check("a plain name beside it is untouched", rows3.get("c2", ("", ""))[:2],
              ("person", "Mum"))
        code, out = run("--from-text",
                        "c1 = " + "x" * 80,
                        "--store", os.path.join(d, "long"), "--tags", tags3)
        check("a name that is 80 characters is REFUSED", "not a name" in out, True)

        print()
        print("5. a missing sheet STOPS rather than silently recording nothing")
        code, out = run("--from-text", "c1 = Mum", "--store", os.path.join(d, "c"),
                        "--tags", tags, "--sheet", os.path.join(d, "no-sheet.html"),
                        "--apply")
        check("it stops", code, 1)
        check("and says why", "no sheet at" in out, True)

        print()
        print("6. the repeat guard covers every round, and is seen FAILING")
        test_repeat_guard(os.path.join(d, "sheets"))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
