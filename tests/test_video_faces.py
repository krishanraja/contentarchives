r"""Prove the video-faces pipeline's guards on fixtures small enough to reason about.

    python tests\test_video_faces.py

Written 2026-09-15 before the pipeline's first full run, because learning 47's
second tell is a guard whose passing path has never executed. Every guard here
is watched both passing AND failing:

  1. FRAME NAMES   every target path is distinct, even for a clip milliseconds
                   long - the probe's whole-second names collided (learning 23)
  2. ABSENT INPUT  --outstanding counts present / failed / outstanding frames, and
                   a library.db whose videos are not on disk STOPS rather than
                   reporting a small set as done (learnings 34, 41)
  3. FROZEN IDS    assign_video_faces never renumbers an existing cluster, puts a
                   matching face INTO it, numbers the rest after it, does not tag a
                   cluster of one, and refuses to tag twice - Krish's answers point
                   at those ids
  4. ALIGNMENT     a face-emb.npy drifted by one row is refused (learning 45)
  5. VERIFIERS     --verify fails on a wrong assignment; --verify-db fails when a
                   named face is missing from photo_people and passes when present
  6. DRY RUN       faces_embed --dry-run counts outstanding and unreadable frames,
                   and ignores half-written .tmp.jpg files
"""

import base64
import csv
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever it lives

import numpy as np                                     # noqa: E402

FAILURES = []
DIM = 512


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def run(script, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, script)] + list(args),
                       capture_output=True, text=True, env=env, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def unit(*axes, noise=0.0):
    v = np.zeros(DIM, dtype=np.float32)
    for ax, w in axes:
        v[ax] += w
    if noise:
        v[100] += noise
    return v / np.linalg.norm(v)


def b64(v):
    return base64.b64encode(v.astype(np.float16).tobytes()).decode("ascii")


def write_csv(p, header, rows):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def H(ch):
    return ch * 64


def test_frame_names():
    print("1. frame names")
    import video_face_frames as V
    for d in (0.0005, 0.003, 0.8, 1.5, 29.9, 45, 179, 7200):
        t = V.targets("X", H("a"), d)
        paths = [p for _, p in t]
        check("distinct paths for a {}s clip".format(d), len(paths), len(set(paths)))
    check("a 2-hour video is capped at 60 frames", len(V.targets("X", H("a"), 7200)), 60)
    check("frame names parse", bool(V.FRAME.match(H("b") + "_t1500.jpg")), True)
    check("a .tmp.jpg is not a frame", bool(V.FRAME.match(H("b") + "_t1500.tmp.jpg")), False)


def test_outstanding(d):
    print()
    print("2. absent input and --outstanding")
    lib = os.path.join(d, "lib")
    os.makedirs(lib)
    frames = os.path.join(d, "frames")
    dbp = os.path.join(d, "lib.db")
    db = sqlite3.connect(dbp)
    db.execute("CREATE TABLE files (path TEXT, hash TEXT, duration REAL, media TEXT)")
    for i, ch in enumerate("abc"):
        p = os.path.join(lib, "v{}.mp4".format(i))
        io.open(p, "wb").write(b"not really a video")
        db.execute("INSERT INTO files VALUES (?,?,?,?)", (p, H(ch), 10.0, "video"))
    db.commit()
    import video_face_frames as V
    a_targets = V.targets(frames, H("a"), 10.0)
    os.makedirs(os.path.dirname(a_targets[0][1]))
    io.open(a_targets[0][1], "wb").write(b"jpg")                   # present
    io.open(V.marker(a_targets[1][1]), "w").write("could not grab")  # failed
    code, out = run("stages/06_faces/video_face_frames.py", "--out", frames, "--db", dbp,
                    "--outstanding")
    m = re.search(r"frames outstanding: (\d+)\s+present: (\d+)\s+failed: (\d+)", out)
    check("--outstanding exits 0", code, 0)
    check("--outstanding counts outstanding/present/failed",
          m.groups() if m else out[-200:], ("4", "1", "1"))

    for i in range(25):                      # rows whose files are not on disk
        db.execute("INSERT INTO files VALUES (?,?,?,?)",
                   (os.path.join(lib, "gone{}.mp4".format(i)), H("%x" % (i % 16)) [:-2] + "%02d" % i,
                    10.0, "video"))
    db.commit()
    db.close()
    code, out = run("stages/06_faces/video_face_frames.py", "--out", frames, "--db", dbp,
                    "--outstanding")
    check("25 of 28 videos missing from disk STOPS the run", code, 1)
    check("and says why", "not on disk" in out, True)

    empty = os.path.join(d, "empty.db")
    e = sqlite3.connect(empty)
    e.execute("CREATE TABLE files (path TEXT, hash TEXT, duration REAL, media TEXT)")
    e.commit()
    e.close()
    code, out = run("stages/06_faces/video_face_frames.py", "--out", frames, "--db", empty)
    check("a library.db with no videos STOPS rather than finishing", code, 1)


def assign_fixture(d):
    """Two frozen clusters, c0 (axis 0) and c1 (axis 1); five video faces."""
    photo_rows, assign_rows, E = [], [], []
    for i, (cl, v) in enumerate([("c0", unit((0, 1), noise=0.05)),
                                 ("c0", unit((0, 1), noise=0.10)),
                                 ("c0", unit((0, 1), noise=0.15)),
                                 ("c1", unit((1, 1), noise=0.05)),
                                 ("c1", unit((1, 1), noise=0.10))]):
        h = H("%x" % (i + 1))
        photo_rows.append([h, 0, "1,1,50,50", "0.900", 1, b64(v)])
        assign_rows.append([h, 0, cl, "0.900", "1,1,50,50"])
        E.append(np.frombuffer(base64.b64decode(b64(v)), dtype=np.float16).astype(np.float32))
    p = {k: os.path.join(d, k) for k in
         ("faces.0.csv", "FACE-CLUSTERS.csv", "face-emb.npy", "faces.video.csv",
          "OUT.csv", "store", "lib.db")}
    write_csv(p["faces.0.csv"], ["hash", "face_index", "bbox", "det_score", "said", "emb"],
              photo_rows)
    write_csv(p["FACE-CLUSTERS.csv"], ["hash", "face_index", "cluster", "det_score", "bbox"],
              assign_rows)
    np.save(p["face-emb.npy"], np.stack(E))
    video = [
        (H("a"), unit((0, 1), noise=0.07)),      # joins c0
        (H("b"), unit((1, 1), noise=0.07)),      # joins c1
        (H("c"), unit((7, 1), noise=0.05)),      # new person...
        (H("d"), unit((7, 1), noise=0.08)),      # ...seen twice
        (H("e"), unit((9, 1))),                  # somebody seen once
    ]
    write_csv(p["faces.video.csv"], ["hash", "image", "face_index", "bbox", "det_score", "emb"],
              [[h, h + "_t500", 0, "1,1,50,50", "0.900", b64(v)] for h, v in video])
    os.makedirs(p["store"])
    write_csv(os.path.join(p["store"], "answers.csv"),
              ["when", "scope", "target", "field", "value", "confidence", "who", "note"],
              [["2026-09-15T10:00:00", "cluster", "c0", "person", "Mum", "1.00", "test", ""]])
    return p


def assign_args(p, *extra):
    return ("--assign", p["FACE-CLUSTERS.csv"], "--cache", p["face-emb.npy"],
            "--photo-faces", p["faces.0.csv"], "--faces", p["faces.video.csv"],
            "--out", p["OUT.csv"], "--merges", os.path.join(os.path.dirname(p["OUT.csv"]), "none.csv"),
            "--store", p["store"], "--db", p["lib.db"]) + extra


def test_assign(d):
    print()
    print("3. frozen cluster ids")
    p = assign_fixture(d)
    before = io.open(p["FACE-CLUSTERS.csv"], "rb").read()
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p, "--apply"))
    check("--apply exits 0", code, 0)
    if code:
        print(out[-600:])
        return p
    check("FACE-CLUSTERS.csv is byte-identical afterwards",
          io.open(p["FACE-CLUSTERS.csv"], "rb").read() == before, True)
    got = {r["hash"][0]: r for r in csv.DictReader(io.open(p["OUT.csv"], encoding="utf-8"))}
    check("a face matching c0 joins c0, not a renumbered id", got["a"]["cluster"], "c0")
    check("a face matching c1 joins c1", got["b"]["cluster"], "c1")
    check("the same new person gets one new id", got["c"]["cluster"], got["d"]["cluster"])
    check("new ids are numbered after the frozen ones",
          int(got["c"]["cluster"][1:]) >= 2 and int(got["e"]["cluster"][1:]) >= 2, True)
    check("two different new people get different ids",
          got["c"]["cluster"] != got["e"]["cluster"], True)
    tags = {(r["hash"][0], r["value"]) for r in
            csv.DictReader(io.open(os.path.join(p["store"], "content_tags.csv"), encoding="utf-8"))
            if r["source"] == "faces-video"}
    check("tags written for joined and repeated faces",
          sorted(tags), sorted({("a", "c0"), ("b", "c1"),
                                ("c", got["c"]["cluster"]), ("d", got["c"]["cluster"])}))
    check("no tag for a cluster of one", any(h == "e" for h, _ in tags), False)
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p, "--apply"))
    check("a second --apply is REFUSED", (code, "REFUSING" in out), (1, True))

    print()
    print("5. verifiers, passing and failing")
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p, "--verify"))
    check("--verify passes on the real assignment", code, 0)
    rows = list(csv.DictReader(io.open(p["OUT.csv"], encoding="utf-8")))
    good = io.open(p["OUT.csv"], encoding="utf-8").read()
    rows[0]["cluster"] = "c1" if rows[0]["cluster"] == "c0" else "c0"
    write_csv(p["OUT.csv"], list(rows[0].keys()), [list(r.values()) for r in rows])
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p, "--verify"))
    check("--verify FAILS when one face is in the wrong cluster", code, 1)
    io.open(p["OUT.csv"], "w", encoding="utf-8", newline="").write(good)

    db = sqlite3.connect(p["lib.db"])
    db.execute("CREATE TABLE photo_people (hash TEXT, person TEXT, source TEXT)")
    db.commit()
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p, "--verify-db"))
    check("--verify-db FAILS when Mum is not on her video", code, 1)
    db.execute("INSERT INTO photo_people VALUES (?,?,?)", (H("a"), "Mum", "human"))
    db.commit()
    db.close()
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p, "--verify-db"))
    check("--verify-db passes once she is", code, 0)
    return p


def test_alignment(d):
    r"""The positional cache is GONE from this tool, so the hazard is too.

    This used to drift `face-emb.npy` by one row and watch the run refuse -
    check_alignment doing its job through assign_video_faces. On 2026-09-23 the
    tool stopped reading that cache at all and joins `faces.0.csv` on
    (hash, face_index) instead, which is learning 45's own durable fix: "not to
    pair by position at all - put the payload in the row that describes it."
    A drifted cache cannot be refused by a tool that never opens it.

    The guard itself is not dead and is not untested: `merge_clusters.py` still
    pairs positionally and still calls it, and `tests/test_guards.py` exercises
    it directly on an aligned cache, a drifted one and a count mismatch. What
    is asserted here now is the property that REPLACED it - a frozen face the
    photograph file cannot produce stops the run, because a centroid built from
    a partial cluster is a wrong centroid and would put wrong names on videos.
    """
    print()
    print("4. alignment")
    p = assign_fixture(d)
    os.remove(p["face-emb.npy"])
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p))
    check("a MISSING positional cache no longer stops the run", code, 0)

    # Take one frozen face out of faces.0.csv: its cluster's centroid would be
    # built from fewer faces than the assignment claims, so the run must refuse.
    rows = list(csv.reader(io.open(p["faces.0.csv"], encoding="utf-8", newline="")))
    with io.open(p["faces.0.csv"], "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows[:-1])
    code, out = run("stages/06_faces/assign_video_faces.py", *assign_args(p))
    check("a frozen face missing from faces.0.csv is refused",
          (code, "STOPPING" in out), (1, True))
    check("  and it says a partial cluster is a wrong centroid",
          "partial cluster" in out, True)


def test_dry_run(d):
    print()
    print("6. faces_embed --dry-run")
    frames = os.path.join(d, "frames")
    sub = os.path.join(frames, "aa")
    os.makedirs(sub)
    for name in (H("a") + "_t100.jpg", H("a") + "_t200.jpg", H("a") + "_t300.jpg",
                 H("a") + "_t400.tmp.jpg", H("a") + "_t500.failed"):
        io.open(os.path.join(sub, name), "wb").write(b"x")
    store = os.path.join(d, "store")
    os.makedirs(store)
    write_csv(os.path.join(store, "faces.video.csv"),
              ["hash", "image", "face_index", "bbox", "det_score", "emb"],
              [[H("a"), H("a") + "_t100", -2, "", "0.000", ""]])
    code, out = run("stages/06_faces/faces_embed.py", "--frames", frames, "--store", store, "--dry-run")
    m = re.search(r"([\d,]+) images to look at, ([\d,]+) already done, ([\d,]+) unreadable", out)
    check("--dry-run exits 0 without loading a model", code, 0)
    check("counts 2 to look at, 1 done, 1 unreadable; ignores .tmp and .failed",
          m.groups() if m else out[-300:], ("2", "1", "1"))
    code, out = run("stages/06_faces/faces_embed.py", "--frames", os.path.join(d, "nope"),
                    "--store", store, "--dry-run")
    check("a frames directory that does not exist STOPS (learning 34)", code != 0, True)


def main():
    test_frame_names()
    for fn in (test_outstanding, test_assign, test_alignment, test_dry_run):
        d = tempfile.mkdtemp()
        try:
            fn(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
