r"""Routing precedence, and the seam where its vocabulary left the repository.

    python tests\test_route_h.py

WHY

route_h.py decides whether a file from a source tree is a memory, produced work,
or admin. It was the one script the publisher refused to publish, because its
production pattern listed employers and projects literally; on 2026-09-16 that
vocabulary moved into the profile beside the library and the logic came into
stage 02.

Two things therefore need watching, and neither is covered by anything else:

  1. THE ORDER OF THE TESTS. Signals are ranked by how self-declaring they are
     (learning 29). A screenshot carries the same \d{8}_\d{6} datestamp a camera
     writes, and when the camera test ran first, thousands of screenshots went
     into the chronology - the one place Krish did not want them. A re-encode
     inherits its original's camera name, which is the same failure again.
  2. THE PROFILE SEAM. With no profile, the employer and project terms are
     simply absent. That must route on the generic half AND SAY SO, not quietly
     file an employer's QA folder as a memory (learning 41).

Verified separately against the machine copy on 6,000 real paths from
H-ROUTING.csv: zero verdict differences.
"""

import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

ROUTE = os.path.join(ROOT, "stages", "02_ingest", "route_h.py")
FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<64} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def load(name="route_under_test", env=None):
    spec = importlib.util.spec_from_file_location(name, ROUTE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    r = load()

    print("1. a file that declares itself beats a pattern that was recognised")
    check("Screenshot_20230105_031931.png is production, not a camera file",
          r.route(r"Pictures\Screenshot_20230105_031931.png")[0], r.PRODUCTION_D)
    check("a plain camera datestamp is a memory",
          r.route(r"Pictures\20230105_031931.jpg")[0], r.CHRONOLOGY)
    check("DJI_0042_youtube_720p.mp4 is a derived copy, not provenance",
          r.route(r"clips\DJI_0042_youtube_720p.mp4")[0], r.PRODUCTION_D)
    check("DJI_0042.mp4 itself is a memory",
          r.route(r"clips\DJI_0042.mp4")[0], r.CHRONOLOGY)

    print()
    print("2. camera names survive being filed badly")
    check("IMG_1234.jpg inside Documents is still a memory",
          r.route(r"Documents\IMG_1234.jpg")[0], r.CHRONOLOGY)
    check("_DSC1215.JPG matches despite the underscore (learnings 20, 30)",
          r.route(r"raw\_DSC1215.JPG")[0], r.CHRONOLOGY)
    check("a document in Documents is archive",
          r.route(r"Documents\tax summary.pdf")[0], r.ARCHIVE)
    check("an identity scan in Pictures is archive, not a photograph",
          r.route(r"Pictures\scans\passport back.jpg")[0], r.ARCHIVE)
    check("audio is never a chronology entry",
          r.route(r"Music\voice note.m4a")[0], r.ARCHIVE)

    print()
    print("3. produced work, from the generic half of the pattern")
    for path in (r"app\node_modules\pkg\logo.png", r"qa-run\shot_001.png",
                 r"exports\wireframe.png"):
        check("production: {}".format(os.path.basename(path)),
              r.route(path)[0], r.PRODUCTION_D)
    check("media with no work signal defaults to a memory",
          r.route(r"holiday 2019\a photo.jpg")[0], r.CHRONOLOGY)
    check("a non-media file is archived visibly, never dropped",
          r.route(r"stuff\installer.apk")[0], r.ARCHIVE)

    print()
    print("4. the profile seam: employer and project terms come from outside the repo")
    from guards.profile import load as load_profile
    prof = load_profile(required=False)
    if prof and prof.production_terms:
        term = prof.production_terms[0]
        check("a profile term routes to production ({})".format(term),
              r.route(os.path.join("work", term, "deck.png"))[0], r.PRODUCTION_D)
    else:
        print("  (no profile on this machine - skipping the positive case)")

    # With no profile at all, the terms are absent. That must be LOUD.
    code = ("import importlib.util,sys;"
            "sys.path.insert(0, r'{root}');"
            "import stagepath;"
            "spec=importlib.util.spec_from_file_location('r', r'{route}');"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
            "print('DEST', m.route(r'work\\\\someproject\\\\deck.png')[0])").format(
        root=ROOT, route=ROUTE)
    env = dict(os.environ, CONTENTARCHIVES_PROFILE=os.path.join(HERE, "no-such-profile.yaml"),
               PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    both = out.stdout + out.stderr
    check("without a profile it warns rather than pretending the list was empty",
          "no profile terms" in both, True)
    check("and it still routes", "DEST" in out.stdout, True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
