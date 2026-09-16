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
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
