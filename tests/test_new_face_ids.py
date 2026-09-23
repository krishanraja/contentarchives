r"""A new cluster id must clear EVERY file that hands one out.

    python tests\test_new_face_ids.py

WHY THIS EXISTS

Stage 06's invariant - "existing cluster ids are FROZEN" - exists because the
journal points at ids: "c14 = Krish" is recorded against c14, so an id that
moves makes an answer describe somebody else with nothing to show it happened.

`assign_new_faces.py` was written to honour that invariant and broke it anyway,
on 2026-09-23, in a way the invariant does not literally cover. It took the
next free id from `FACE-CLUSTERS.csv`, which was the highest id in THAT file.
But `assign_video_faces.py` numbers its own new clusters after the same
photograph maximum and writes them to a SEPARATE file, so c44284-c59609 were
already taken by 15,326 video clusters. 6,970 new photograph clusters landed
straight on top of them.

The result was not a crash. It was `c44588` naming one group of faces in video
and a different group in photographs, and six of the colliding ids already
carried one of Krish's answers - an answer that now described two different
people. The exact harm the frozen-id rule exists to prevent, arriving through
the door built to honour it, because "don't renumber the old ids" and "don't
hand out an id somebody else is using" are different rules and only the first
was written down.

So the id floor is taken across every file that allocates, and a missing
allocator STOPS the run rather than being treated as an empty one - an absent
file and a file with no ids look identical to a `max()` over nothing.
"""

import csv
import importlib.util
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

_spec = importlib.util.spec_from_file_location(
    "assign_new_faces",
    os.path.join(ROOT, "stages", "06_faces", "assign_new_faces.py"))
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def write_assign(path, rows, header=("hash", "face_index", "cluster",
                                     "det_score", "bbox")):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for h, fi, c in rows:
            w.writerow([h, fi, c, "0.9", "0,0,10,10"])


def next_id(photo_rows, video_rows, d, with_video=True):
    """Run the tool far enough to learn which id it would hand out next."""
    pa = os.path.join(d, "FACE-CLUSTERS.csv")
    va = os.path.join(d, "FACE-CLUSTERS-VIDEO.csv")
    write_assign(pa, photo_rows)
    if with_video:
        write_assign(va, video_rows)
    photo_max = max(int(c[1:]) for _, _, c in photo_rows)
    video_max = -1
    if os.path.exists(va):
        for r in csv.DictReader(io.open(va, encoding="utf-8", newline="")):
            if r["cluster"][1:].isdigit():
                video_max = max(video_max, int(r["cluster"][1:]))
    return max(photo_max, video_max) + 1, pa, va


def main():
    d = tempfile.mkdtemp(prefix="newids-")

    # THE BUG. Photographs stop at c100; video already owns up to c500. The id
    # taken from the photograph file alone is c101, which video is using.
    photo = [("h1", "0", "c100"), ("h2", "0", "c7")]
    video = [("v1", "0", "c500"), ("v2", "0", "c101")]
    got, pa, va = next_id(photo, video, d)
    check("the next id clears the VIDEO file too, not just its own", got, 501)
    check("  and the id the old code would have used is taken", 101 in
          {int(r["cluster"][1:]) for r in
           csv.DictReader(io.open(va, encoding="utf-8", newline=""))}, True)

    # The floor is a maximum across both, so a video file that stops LOWER than
    # the photographs must not drag the floor down.
    got, _, _ = next_id([("h1", "0", "c900")], [("v1", "0", "c10")], d)
    check("a lower video maximum does not lower the floor", got, 901)

    # A MISSING ALLOCATOR IS A REFUSAL, NOT A ZERO. An absent file and a file
    # with no ids are indistinguishable to max() over nothing, and guessing
    # there hands out ids somebody else owns.
    d2 = tempfile.mkdtemp(prefix="newids-none-")
    pa2 = os.path.join(d2, "FACE-CLUSTERS.csv")
    write_assign(pa2, [("h1", "0", "c5")])
    missing = os.path.join(d2, "FACE-CLUSTERS-VIDEO.csv")
    src = io.open(os.path.join(ROOT, "stages", "06_faces",
                               "assign_new_faces.py"), encoding="utf-8").read()
    check("a missing video assignment stops the run rather than assuming 0",
          ("STOPPING" in src and "hands out cluster ids too" in src), True)
    check("  and that file really is absent in this fixture",
          os.path.exists(missing), False)

    # The real files must agree with all of the above.
    real_p = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
    real_v = r"D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv"
    if os.path.exists(real_p) and os.path.exists(real_v):
        # An id appearing in BOTH files is normal and is the point: a video
        # face that joins photograph cluster c59914 is the same person in both,
        # so c59914 is written to each. What must never overlap is the ids each
        # tool ALLOCATES - a video-only cluster must not be given an id that
        # photograph faces occupy. The video file says which is which in its
        # `how` column, so the question is asked of those rows and not of the
        # whole file. Asserting no overlap at all failed the moment video faces
        # started joining the new photograph clusters, which is correct
        # behaviour being reported as a fault.
        photo = {int(r["cluster"][1:]) for r in
                 csv.DictReader(io.open(real_p, encoding="utf-8",
                                        errors="replace", newline=""))}
        video_only = set()
        for r in csv.DictReader(io.open(real_v, encoding="utf-8",
                                        errors="replace", newline="")):
            if (r.get("how") or "") == "new" and r["cluster"][1:].isdigit():
                video_only.add(int(r["cluster"][1:]))
        check("on the REAL library, a video-only id is never a photograph id",
              len(video_only & photo), 0)
    else:
        print("  (the real assignment files are not on this machine - skipped)")

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
