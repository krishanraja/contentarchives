r"""merge_clusters.py builds its centroids by KEY, and needs no face-emb.npy.

    python tests\test_merge_clusters.py

WHY

On 2026-10-16 the first app sync since the cloud took over died in the merge
step: `face-emb.npy`, the positional cache merge_clusters.py read, does not
exist on the library machine (RESUME.md had said so for weeks). Both nightly
chains carry on past a non-zero merge, so names had silently stopped reaching
sibling clusters. The fix is learning 45's own: read each embedding from the
`faces.0.csv` row that carries its (hash, face_index), never by row number.

WHAT IT PINS

  1. The run needs no cache at all, and merges the right clusters when
     faces.0.csv is in a DIFFERENT ORDER from FACE-CLUSTERS.csv - the case a
     positional pairing gets wrong: here it would average one person's faces
     into another person's cluster.
  2. --apply writes the merge group and gives the unnamed sibling the name as a
     DERIVED tag, never touching the answers journal.
  3. A frozen face the photograph file cannot produce stops the run: a partial
     cluster is a wrong centroid.
  4. Two named people are still never merged.
"""

import base64
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIM = 512
FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<66} {}".format(name, "OK" if ok else "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "stages", "06_faces", "merge_clusters.py")]
                       + list(args), capture_output=True, text=True, env=env, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def emb(axis, wobble):
    v = np.zeros(DIM, dtype=np.float32)
    v[axis] = 1.0
    v[200 + wobble] = 0.15                      # each face a little different
    v /= np.linalg.norm(v)
    return base64.b64encode(v.astype(np.float16).tobytes()).decode("ascii")


def fixture(d, names):
    """Two people. Person A (axis 0) is split over c1 and c2; person B (axis 1) is c3."""
    faces = [  # (hash, face_index, cluster, axis)
        ("ha1", "0", "c1", 0), ("ha2", "0", "c1", 0), ("ha3", "1", "c1", 0),
        ("ha4", "0", "c2", 0), ("ha5", "0", "c2", 0), ("ha6", "2", "c2", 0),
        ("hb1", "0", "c3", 1), ("hb2", "0", "c3", 1), ("hb3", "1", "c3", 1),
    ]
    p = {k: os.path.join(d, k) for k in ("FACE-CLUSTERS.csv", "faces.0.csv", "answers.csv",
                                         "CLUSTER-MERGES.csv", "store")}
    os.makedirs(p["store"], exist_ok=True)
    with io.open(p["FACE-CLUSTERS.csv"], "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hash", "face_index", "cluster"])
        for h, fi, c, _ in faces:
            w.writerow([h, fi, c])
    # THE OTHER ORDER: reversed, plus an unassigned face and a no-face marker.
    # Paired by row number, c1 (person A) would be averaged from person B's
    # faces and c3 from person A's - and the wrong pair would merge.
    with io.open(p["faces.0.csv"], "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hash", "face_index", "score", "emb"])
        w.writerow(["hz9", "0", "0.9", emb(5, 9)])           # in no cluster
        w.writerow(["hz8", "-1", "", ""])                     # a photo with no face
        for n, (h, fi, c, axis) in enumerate(reversed(faces)):
            w.writerow([h, fi, "0.9", emb(axis, n)])
    with io.open(p["answers.csv"], "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["when", "scope", "target", "field", "value", "confidence", "who", "note"])
        for c, name in names.items():
            w.writerow(["2026-10-16T00:00:00", "cluster", c, "person", name, "1.0", "test", ""])
    return p


def args(p, *more):
    return ["--assign", p["FACE-CLUSTERS.csv"], "--photo-faces", p["faces.0.csv"],
            "--video-assign", os.path.join(p["store"], "none.csv"),
            "--video-faces", os.path.join(p["store"], "none.csv"),
            "--answers", p["answers.csv"], "--out", p["CLUSTER-MERGES.csv"],
            "--store", p["store"], "--min-faces", "1", "--threshold", "0.70"] + list(more)


def main():
    d = tempfile.mkdtemp()
    try:
        print("1. no cache, and the right clusters merge when the files disagree on order")
        p = fixture(d, {"c1": "Asha", "c3": "Ravi"})
        check("there is no face-emb.npy anywhere in the fixture",
              any(f.endswith(".npy") for _, _, fs in os.walk(d) for f in fs), False)
        code, out = run(*args(p))
        check("the dry run exits 0", code, 0)
        check("every frozen face is found by key", "found in faces.0.csv by (hash, face_index): 9" in out, True)
        check("one merge: A's two clusters, and B stays apart", "1 merges, 1 groups of more than one" in out, True)
        check("no named person is mixed with another", "no group mixes two differently-named" in out, True)

        print()
        print("2. --apply writes the group and a DERIVED name, never the journal")
        journal = io.open(p["answers.csv"], encoding="utf-8").read()
        code, out = run(*args(p, "--apply"))
        check("--apply exits 0", code, 0)
        groups = {r["cluster"]: r for r in csv.DictReader(io.open(p["CLUSTER-MERGES.csv"], encoding="utf-8"))}
        check("c1 and c2 share a group", groups["c1"]["group"] == groups["c2"]["group"], True)
        check("c3 is in a group of its own", groups["c3"]["group"] not in (groups["c1"]["group"],), True)
        check("the unnamed sibling inherits the name as cluster-merge",
              (groups["c2"]["person"], groups["c2"]["source"]), ("Asha", "cluster-merge"))
        tags = [r for r in csv.DictReader(io.open(os.path.join(p["store"], "content_tags.csv"), encoding="utf-8"))
                if r["tag"] == "person"]
        check("each of c2's photographs gets the derived tag",
              sorted(r["hash"] for r in tags if r["value"] == "Asha"), ["ha4", "ha5", "ha6"])
        check("and nothing of B's is named A",
              any(r["hash"].startswith("hb") and r["value"] == "Asha" for r in tags), False)
        check("the answers journal is untouched",
              io.open(p["answers.csv"], encoding="utf-8").read() == journal, True)

        print()
        print("3. a frozen face missing from faces.0.csv stops the run")
        rows = list(csv.reader(io.open(p["faces.0.csv"], encoding="utf-8", newline="")))
        with io.open(p["faces.0.csv"], "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows([r for r in rows if r[0] != "ha2"])
        code, out = run(*args(p))
        check("it refuses", (code, "STOPPING" in out), (1, True))
        check("  and says a partial cluster is a wrong centroid", "partial cluster" in out, True)

        print()
        print("4. two named people are still never merged")
        d2 = tempfile.mkdtemp()
        try:
            p2 = fixture(d2, {"c1": "Asha", "c2": "Meera"})
            code, out = run(*args(p2))
            check("a group holding two different names refuses", (code, "REFUSING TO MERGE" in out), (1, True))
        finally:
            shutil.rmtree(d2, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
