r"""Watch the path bootstrap resolve, and fail, before anything depends on it.

    python tests\test_stagepath.py

stagepath.py is on the critical path of every stage script: if it silently
resolves a name to the wrong file, or returns something that does not exist, the
failure lands in a subprocess hours into a chain. So its failing path is watched
here too (learning 47's second tell), and every directory it claims to have added
is checked to exist (learning 34).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import stagepath                                            # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def main():
    dirs = stagepath.dirs()
    check("it added at least one directory", len(dirs) > 0, True)
    check("every directory it added exists", all(os.path.isdir(d) for d in dirs), True)
    check("every directory it added is on sys.path", all(d in sys.path for d in dirs), True)
    check("the repo root is on sys.path", ROOT in sys.path, True)

    # a file that certainly exists somewhere on the conveyor
    known = "build_db.py"
    p = stagepath.script(known)
    check("script() resolves a real file", os.path.isfile(p), True)
    check("script() returns it by its own name", os.path.basename(p), known)

    missing = "no_such_script_ever.py"
    try:
        stagepath.script(missing)
        check("script() STOPS on a name that does not exist", "returned", "SystemExit")
    except SystemExit as e:
        check("script() STOPS on a name that does not exist", "STOPPING" in str(e), True)
        check("and names the directories it searched", str(e).count(os.sep) > 0, True)
    check("find() returns None instead of stopping", stagepath.find(missing), None)
    check("find() resolves a real file", os.path.isfile(stagepath.find(known) or ""), True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
