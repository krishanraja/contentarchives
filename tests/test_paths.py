r"""The machine half of the configuration: one definition, and loud when absent.

    python tests\test_paths.py

WHY

Five scripts carried this, each its own copy:

    FFPROBE = (r"C:\Users\user\AppData\Local\Microsoft\WinGet\Packages"
               r"\Gyan.FFmpeg_...\ffprobe.exe")

One machine's username, hardcoded. On this machine the user is `krish`, so the
path did not exist - and `probe_video()` returned an empty dict when the binary
was missing, so a 33-minute pass wrote no Duration, Width or Height for any of
12,988 videos and reported success (learning 41).

So the binary is resolved, not asserted: shutil.which first, then a glob under
the CURRENT user, and a missing tool raises rather than returning "". These
checks watch that raise, because a helper that returns a falsy path on failure
is the same bug wearing a different hat.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "guards"))

import paths as P                                            # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def main():
    print("1. the library tree is one definition")
    for attr in ("ROOT", "MEDIA", "PERSONAL", "COMMUNAL", "NODATE", "PENDING",
                 "ARCHIVE", "REVIEW", "CATALOG", "AUDIT"):
        check("paths.{} is defined".format(attr), hasattr(P, attr), True)
    check("every chronology tree sits under MEDIA",
          all(str(p).startswith(str(P.MEDIA)) for p in P.CHRONOLOGY), True)

    # The mounts material comes FROM and the drive it is backed up TO. Three
    # scripts each carried their own copy of the H: root and two carried
    # G:\My Drive. A second definition is how a script comes to survey a folder
    # that has moved and report that it is empty.
    for attr in ("H_ROOT", "H_STAGE", "GDRIVE"):
        check("paths.{} is defined".format(attr), hasattr(P, attr), True)
    check("no mount is nested inside the library",
          any(str(getattr(P, a)).lower().startswith(str(P.ROOT).lower())
              for a in ("H_ROOT", "H_STAGE", "GDRIVE")), False)

    print()
    print("2. tools are resolved, never hardcoded to one machine's username")
    check("no path under another user's profile",
          any("Users\\user\\" in str(v) for v in vars(P).values() if isinstance(v, str)),
          False)
    check("FFPROBE is a resolver, not a constant string",
          callable(getattr(P, "ffprobe", None)), True)
    got = P.ffprobe(required=False)
    check("it resolves ffprobe on this machine", bool(got) and os.path.exists(got), True)
    check("ffmpeg too", bool(P.ffmpeg(required=False)), True)

    print()
    print("3. a missing tool RAISES rather than returning an empty string")
    try:
        P._resolve("definitely-not-a-real-binary-xyz", required=True)
        check("a missing binary stops", "returned", "SystemExit")
    except SystemExit as e:
        check("a missing binary stops", "STOPPING" in str(e), True)
        check("and says which binary", "definitely-not-a-real-binary-xyz" in str(e), True)
    check("required=False returns None, not ''",
          P._resolve("definitely-not-a-real-binary-xyz", required=False), None)

    print()
    print("4. scratch and sources are declared in one place")
    check("SCRATCH_DIRS exists and is a list", isinstance(P.SCRATCH_DIRS, list), True)
    check("no scratch dir sits inside the library",
          any(str(s).lower().startswith(str(P.ROOT).lower()) for s in P.SCRATCH_DIRS),
          False)
    check("SOURCES exists", isinstance(P.SOURCES, list), True)
    check("WATCH_DIRS exists", isinstance(P.WATCH_DIRS, list), True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
