r"""Watch every guard in guards/ pass AND fail.

    python tests\test_guards.py

A guard whose failing path has never run is untested code holding a veto
(learning 47, second tell). Each check below is referenced by name from a
STAGE.md Lessons table, and tests/test_stage_contracts.py fails if the name
stops existing here.
"""

import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                          # noqa: E402

from guards.alignment import check_alignment                # noqa: E402
from guards.files import (atomic_write_text, atomic_writer,  # noqa: E402
                          complete_lines, require_dir, require_file)
from guards.verify import CANNOT_TELL, OK, WRONG, verdict   # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<60} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def stops(fn, *a):
    try:
        fn(*a)
    except SystemExit as e:
        return "STOPPING" in str(e)
    return False


def main():
    d = tempfile.mkdtemp()
    try:
        print("files (learnings 34, 41, 42)")
        p = os.path.join(d, "out.csv")
        atomic_write_text(p, "old\n")
        try:
            with atomic_writer(p) as f:
                f.write("half a new fi")
                raise RuntimeError("killed mid-write")
        except RuntimeError:
            pass
        check("a reader never sees a partial file",
              io.open(p, encoding="utf-8").read(), "old\n")
        check("a failed write leaves no .tmp behind", os.path.exists(p + ".tmp"), False)
        with atomic_writer(p) as f:
            f.write("new\n")
        check("a finished write replaces the file", io.open(p, encoding="utf-8").read(), "new\n")

        check("a missing directory stops", stops(require_dir, os.path.join(d, "nope")), True)
        check("an existing directory passes", require_dir(d), d)
        check("a missing file stops", stops(require_file, os.path.join(d, "nope.csv")), True)
        check("an existing file passes", require_file(p), p)

        q = os.path.join(d, "growing.csv")
        io.open(q, "w", encoding="utf-8", newline="").write("a,1\nb,2\nc,")
        with io.open(q, encoding="utf-8", newline="") as f:
            got = list(complete_lines(f))
        check("a half-written last line is left out", got, ["a,1\n", "b,2\n"])
        io.open(q, "w", encoding="utf-8", newline="").write("a,1\nb,2\n")
        with io.open(q, encoding="utf-8", newline="") as f:
            got = list(complete_lines(f))
        check("a finished last line is kept", got, ["a,1\n", "b,2\n"])

        print()
        print("verify contract (learnings 6, 46)")
        check("nothing re-derived is a failure", verdict(5, 0, 0), WRONG)
        check("a mismatch is a failure", verdict(5, 5, 1), WRONG)
        check("nothing to sample yet is can't-tell", verdict(0, 0, 0), CANNOT_TELL)
        check("a clean sample passes", verdict(5, 5, 0), OK)

        print()
        print("alignment (learning 45)")
        import base64
        import csv
        vecs = []
        for i in range(6):
            v = np.zeros(512, dtype=np.float32)
            v[i] = 1.0
            vecs.append(v)
        src = os.path.join(d, "faces.csv")
        with io.open(src, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["hash", "face_index", "emb"])
            for i, v in enumerate(vecs):
                w.writerow([str(i) * 64, 0, base64.b64encode(v.astype(np.float16).tobytes()).decode()])
        rows = [{"hash": str(i) * 64, "face_index": 0} for i in range(6)]
        E = np.stack(vecs)
        check("an aligned cache passes", check_alignment(rows, E, src), [])
        check("a drifted cache is caught", bool(check_alignment(rows, np.roll(E, 1, axis=0), src)), True)
        check("a count mismatch is caught", bool(check_alignment(rows, E[:5], src)), True)

        # A PURGED FACE IS NOT A DRIFTED ONE.
        #
        # Krish, 2026-09-18: "purge all intimate content forever". A purged
        # face's embedding is overwritten with zeros IN PLACE, so the row keeps
        # its position and therefore the frozen cluster id his 1,609 answers
        # point at. But cosine is undefined for a zero vector - np.dot returns
        # 0.0, which fails the 0.99 test and reads as the loudest alarm this
        # project has. Measured on a fixture before the real purge ran: a
        # zeroed row reported "cosine 0.000 with its source".
        #
        # So both-zero must pass, and exactly-one-zero must still be caught:
        # a purge that reached the source but not the cache, or the reverse,
        # is genuine disagreement and hides a real face behind a blank row.
        zsrc = os.path.join(d, "faces_purged.csv")
        zvecs = [v.copy() for v in vecs]
        zvecs[3] = np.zeros(512, dtype=np.float32)
        with io.open(zsrc, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["hash", "face_index", "emb"])
            for i, v in enumerate(zvecs):
                w.writerow([str(i) * 64, 0,
                            base64.b64encode(v.astype(np.float16).tobytes()).decode()])
        check("a purged row passes when source AND cache are zeroed",
              check_alignment(rows, np.stack(zvecs), zsrc), [])
        check("zeroed in the source but not the cache is CAUGHT",
              bool(check_alignment(rows, E, zsrc)), True)
        check("zeroed in the cache but not the source is CAUGHT",
              bool(check_alignment(rows, np.stack(zvecs), src)), True)
        check("and the message says a purge reached one and not the other",
              any("not the other" in p
                  for p in check_alignment(rows, E, zsrc)), True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
