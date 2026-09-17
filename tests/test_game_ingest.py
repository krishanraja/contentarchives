r"""The phone games write to the journal unattended. Prove it cannot do harm twice.

    python tests\test_game_ingest.py

Krish, 2026-09-18: *"you need to account for the fact that this session might be
closed when I am on my phone doing the classification game, and that there are
likely to be a lot of repeated names. make it antifragile, perhaps on a biweekly
basis you can auto check for new data and integrate it safely"*.

A scheduled job that nobody is watching writes to the ONE file in this project
that money and compute cannot reproduce. So the three behaviours pinned here are
the ones that are invisible when they break:

  1. IDEMPOTENCE. Running the same rows again records nothing. A fortnightly job
     that re-reads the same artifact database must not append the same answer
     fifty times over a year.
  2. NAME FOLDING, and its limit. "lauren " becomes the "Lauren" already in the
     journal; "Laurenn" stays "Laurenn". A machine deciding two SIMILAR names
     are one person is exactly how the two Kirans and the three Rishis happened.
  3. REFUSAL. A cluster id the tag store does not hold is refused, not recorded -
     a typo would label somebody else's photographs and look like success.

Watched FAILING as well as passing: a guard nobody has seen reject is
indistinguishable from no guard (learning 44).
"""

import csv
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

import ingest_game_answers as G                                  # noqa: E402
from answers import Journal                                      # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def fixture(d):
    """A store with two known clusters and one name already answered."""
    store = os.path.join(d, "store")
    os.makedirs(store, exist_ok=True)
    with io.open(os.path.join(store, "content_tags.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hash", "tag", "value", "source", "confidence", "when"])
        for cid in ("c1", "c2", "c3"):
            w.writerow(["h" + cid, "cluster", cid, "faces", "1.0", "x"])
    j = Journal(store, who="krish")
    j.record("cluster", "c1", "person", "Lauren")
    return store


def run(rows, store, cursor, who="krish", apply=True):
    p = os.path.join(os.path.dirname(cursor), "rows.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(rows))
    argv = sys.argv
    try:
        sys.argv = ["ingest_game_answers.py", "--rows", p, "--store", store,
                    "--tags", os.path.join(store, "content_tags.csv"),
                    "--cursor", cursor, "--who", who] + (["--apply"] if apply else [])
        return G.main()
    finally:
        sys.argv = argv


def persons(store):
    j = Journal(store)
    return [(r["target"], r["field"], r["value"], r["who"])
            for r in j.all_rows()]


def main():
    d = tempfile.mkdtemp()
    store = fixture(d)
    cursor = os.path.join(d, "cursor.json")

    print("1. a first ingest records the new answers")
    rows = [{"id": "r1", "cluster": "c2", "name": "Bhasker"},
            {"id": "r2", "cluster": "c3", "name": "for Bharti"}]
    check("it exits 0", run(rows, store, cursor), 0)
    got = persons(store)
    check("the name is recorded", ("c2", "person", "Bhasker", "krish") in got,
          True)
    check("'for Bharti' is a QUESTION, never a person called 'for Bharti'",
          ("c3", "needs_identifying", "Bharti", "krish") in got, True)
    n_after_first = len(got)

    print()
    print("2. IDEMPOTENCE: the same rows again record nothing")
    check("it exits 0 again", run(rows, store, cursor), 0)
    check("the journal did not grow", len(persons(store)), n_after_first)

    print()
    print("3. name folding, and the line it will not cross")
    rows2 = [{"id": "r3", "cluster": "c2", "name": "lauren "},
             {"id": "r4", "cluster": "c3", "name": "Laurenn"}]
    run(rows2, store, cursor)
    got = persons(store)
    check("'lauren ' folds onto the existing 'Lauren'",
          ("c2", "person", "Lauren", "krish") in got, True)
    check("'Laurenn' is NOT folded - similarity is never enough",
          ("c3", "person", "Laurenn", "krish") in got, True)

    print()
    print("4. a cluster the store does not hold is REFUSED")
    before = len(persons(store))
    check("it still exits 0 (a refusal is not a crash)",
          run([{"id": "r5", "cluster": "c999", "name": "Nobody"}],
              store, cursor), 0)
    check("and nothing was recorded", len(persons(store)), before)

    print()
    print("5. Bharti's answers carry HER provenance, in the same journal")
    run([{"id": "r6", "cluster": "c2", "name": "Jyoti"}], store, cursor,
        who="bharti")
    check("who=bharti", ("c2", "person", "Jyoti", "bharti") in persons(store),
          True)

    print()
    print("6. a corrupt cursor costs duplicates, never a lost answer")
    io.open(cursor, "w", encoding="utf-8").write("{not json")
    before = len(persons(store))
    check("it exits 0 rather than refusing to run",
          run([{"id": "r7", "cluster": "c3", "name": "Dipti"}],
              store, cursor), 0)
    check("the answer is still recorded", len(persons(store)), before + 1)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
