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
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
