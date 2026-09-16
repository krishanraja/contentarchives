r"""The profile holds what the repo must never hold. Watch it refuse to guess.

    python tests\test_profile.py

WHY

Until 2026-09-16 personal detail lived in the code and was redacted on
publication, which produced a public copy nobody could run and left the only
runnable one on a single disk. guards/profile.py moves that detail into a file
beside the library, uncommitted.

The danger in doing so is learning 41: a missing profile that reads as "no
personal terms" turns every protection over Krish's own material into a no-op
and reports success. So the checks below watch it STOP - on an absent file, and
on a present file with an empty term list, which look identical to a caller and
are equally disabling.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from guards import profile as P                               # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def load_in(path):
    """load() in a subprocess, so SystemExit text is captured whole."""
    code = ("import sys; sys.path.insert(0, r'{root}');"
            "from guards.profile import load; p = load();"
            "print('LOADED', p.name, len(p.personal_terms))").format(root=ROOT)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, CONTENTARCHIVES_PROFILE=path,
                                PYTHONIOENCODING="utf-8"))
    return r.returncode, r.stdout + r.stderr


# A term may match at most this share of the library.
#
# THE FIRST VERSION OF THIS NUMBER WAS 2%, AND IT WAS WRONG IN EXACTLY THE WAY
# learning 54 DESCRIBES. It was derived from the 33 restored terms, whose worst
# case is 0.04%, without once measuring the terms already in the profile. Four
# of those exceed 2% and every one of them is correct and load-bearing:
#
#     old photos      4,958 paths   6.03%    a real library folder name
#     bharti          3,147 paths   3.83%    the second most photographed person
#     bharti phone    3,126 paths   3.80%    a real library folder name
#     krish              >2%                 the most photographed person
#
# A term matching a lot of the library is not evidence of anything: Krish
# appears in 9,088 photographs because it is his library. What this check can
# honestly catch is a CATCH-ALL - a term like "img", "photo" or "dcim" that
# would mark nearly everything personal and make the protection meaningless.
# So the line sits where a term stops describing a subject and starts
# describing the medium.
TOO_BROAD = 0.50


def library_paths():
    """Real library paths, or None when this machine has no index to measure.

    READ-ONLY, and closed before returning. On 2026-09-16 a 19-minute rebuild
    finished its work and then died on `os.replace(library.db.tmp, library.db)`
    with WinError 5, because a reader still held the live database open. A test
    that measures the library must never be the reason the library cannot be
    rebuilt: mode=ro takes no write lock, creates no -wal, and the connection is
    closed even when the query raises.
    """
    import sqlite3
    db_path = r"D:\_PhotoAudit\library.db"
    if not os.path.isfile(db_path):
        return None
    uri = "file:{}?mode=ro".format(db_path.replace("\\", "/"))
    db = None
    try:
        db = sqlite3.connect(uri, uri=True)
        return [r[0].lower() for r in db.execute("select path from files")]
    except sqlite3.Error:
        return None
    finally:
        if db is not None:
            db.close()


def test_no_term_is_too_broad():
    """Count every live profile term against the library. Never assume.

    84 terms were once dropped from the profile because a comment said a short
    name "would mark half the library personal". Nobody counted. The worst of
    them matched 0.04%, and the drop had left people Krish had just named
    outside the rule that protects his own material (learning 54).
    """
    prof = P.load(required=False)
    if prof is None:
        print("  (no profile on this machine - nothing to measure)")
        return
    paths = library_paths()
    if paths is None:
        print("  (no library index on this machine - nothing to measure against)")
        return
    total = len(paths)
    print("  measuring {} terms against {:,} real library paths".format(
        len(prof.personal_terms), total))
    worst = []
    for term in prof.personal_terms:
        n = sum(1 for p in paths if term in p)
        worst.append((n / max(total, 1), n, term))
    worst.sort(reverse=True)
    for share, n, term in worst[:3]:
        print("    widest: {:<18} {:>7,} paths  {:.2f}%".format(term, n, share * 100))
    over = [(t, n, s) for s, n, t in worst if s > TOO_BROAD]
    check("no term is a catch-all (over {:.0%} of the library)".format(TOO_BROAD),
          [t for t, _, _ in over], [])
    # The widest term is reported every run, so a new catch-all is visible in the
    # output long before it crosses the line. A threshold is not a substitute for
    # reading what it measured.
    print("    (widest is {:.2f}%; the line is at {:.0%})".format(
        worst[0][0] * 100 if worst else 0.0, TOO_BROAD))
    # And the protection actually covers the people Krish named this week.
    for name in ("tima", "max", "olly"):
        check("{} is protected".format(name),
              prof.is_personal(r"D:\ContentLibrary\Media\Personal\2019\{}.jpg".format(name)),
              True)


JOURNAL = r"D:\_enrichment\answers.csv"


def named_people(journal=JOURNAL):
    """Every person named in the answers journal, or None if it is not here."""
    import csv
    import re
    if not os.path.isfile(journal):
        return None
    out = set()
    with io.open(journal, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("field") != "person" or not row.get("value"):
                continue
            v = re.sub(r"\s*\(.*?\)\s*", " ", row["value"]).strip()
            if not v or v.lower().startswith(("for ", "unsure")):
                continue
            out.add(v.lower())
    return out


def test_every_named_person_is_protected():
    r"""A person Krish took the trouble to name must be covered by the rule.

    A profile term means THIS MATTERS: never swept, never compressed, never
    deleted, overriding every exclusion. The profile is SEEDED from these same
    answers - so a name in the journal and not in the profile is a gap, not a
    choice.

    Owned by learning 54, not learning 1. Learning 1 is about DELETION - a path
    is never sufficient grounds, prove the bytes exist elsewhere first - and
    10 reclaim enforces it with safety.py's allowlist and the test that refuses
    the file which was actually lost. Citing it here would stretch it to cover a
    claim it does not make. What this check is really about is a measurement that
    reported success while measuring the wrong thing, which is learning 54.

    It silently held 27 of 222 for most of a day. The seeding script kept a
    single name only if it was five or more characters, which dropped Lily
    (1,724 photographs, named in round 4), Mak (444), JY (515), Mami, Adil,
    Rani, Blainey and twenty more - and every per-round top-up after that
    considered only THAT round's new names, so nobody dropped at the start was
    ever revisited. Eight rounds of "the profile is seeded from his answers"
    were true of the process and false of the result.

    Asked through is_personal() on a real-shaped path, never by comparing names
    to the term list, which was wrong three times in one afternoon (learning 54).
    """
    prof = P.load(required=False)
    if prof is None:
        print("  (no profile on this machine - nothing to check)")
        return
    people = named_people()
    if people is None:
        print("  (no answers journal on this machine - nothing to check)")
        return
    missing = sorted(n for n in people
                     if not prof.is_personal(
                         r"D:\ContentLibrary\Media\Personal\2024\{} at dinner.jpg".format(n)))
    print("  {} people named in the journal".format(len(people)))
    check("every one of them is protected", missing, [])


def main():
    d = tempfile.mkdtemp()
    try:
        print("1. an absent profile stops, and says what is missing")
        code, out = load_in(os.path.join(d, "nope.yaml"))
        check("it stops", code != 0, True)
        check("it names the environment variable", P.ENV in out, True)
        check("it points at the example", "profiles/example.yaml" in out, True)

        print()
        print("2. a profile with no personal terms also stops")
        empty = os.path.join(d, "empty.yaml")
        io.open(empty, "w", encoding="utf-8").write(
            "name: test\nsafety:\n  personal_terms: []\n")
        code, out = load_in(empty)
        check("it stops", code != 0, True)
        check("and says an empty list disables the rule", "no-op" in out or "disable" in out, True)

        print()
        print("3. a real profile loads and matches")
        good = os.path.join(d, "good.yaml")
        io.open(good, "w", encoding="utf-8").write(
            "name: test-job\n"
            "safety:\n"
            "  personal_terms:\n    - whatsapp\n    - surname\n"
            "  review_hints:\n    - downloads\n"
            "  confirm_deletions: true\n")
        code, out = load_in(good)
        check("it loads", (code, "LOADED test-job 2" in out), (0, True))
        os.environ[P.ENV] = good
        p = P.load()
        check("a term inside an underscored filename matches",
              p.is_personal(r"D:\x\2019_surname_phone\IMG_0001.jpg"), True)
        check("an unrelated path does not", p.is_personal(r"D:\x\node_modules\a.png"), False)
        check("review hints are separate from personal terms",
              (p.needs_review(r"C:\Users\x\Downloads\a.mp4"),
               p.is_personal(r"C:\Users\x\Downloads\a.mp4")), (True, False))
        check("deletions still need confirming", p.confirm_deletions, True)

        print()
        print("4. an optional caller gets None rather than a stop")
        os.environ[P.ENV] = os.path.join(d, "nope.yaml")
        check("load(required=False) returns None", P.load(required=False), None)
    finally:
        os.environ.pop(P.ENV, None)
        shutil.rmtree(d, ignore_errors=True)

    print()
    print("5. no term is too broad - MEASURED, not assumed (learning 54)")
    test_no_term_is_too_broad()

    print()
    print("6. EVERY person Krish has named is protected (learning 54)")
    test_every_named_person_is_protected()

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
