r"""Put video faces into the clusters Krish has already named. Never renumber.

    python assign_video_faces.py              # report, write nothing
    python assign_video_faces.py --apply
    python assign_video_faces.py --verify     # 0 right, 1 wrong, 2 nothing written yet
    python assign_video_faces.py --verify-db  # did named video faces reach library.db?

WHY NOT RE-RUN cluster_faces.py

Cluster ids are what Krish's answers point at: "c14 = Krish" is recorded against
c14. cluster_faces.py numbers clusters in the order it meets them, so feeding it
thirty thousand more faces renumbers everything, and every answer in the journal
would silently point at somebody else - with nothing to show it had happened,
because each answer would still land on a real cluster.

So the existing clusters are FROZEN. A video face joins the existing cluster
whose centroid it matches, at the same 0.55 the photographs were clustered at.
That is how a frame of Krish at 3:40 into a video becomes a photograph of Krish
without anybody being asked. Faces that match nobody are clustered among
themselves, best-detected first, and numbered after the highest existing id.

THE FROZEN CENTROIDS ARE CHECKED BEFORE THEY ARE USED

They are built from face-emb.npy, which is matched to FACE-CLUSTERS.csv BY
POSITION. That is the exact shape of learning 45, and a row-count check cannot
see a drift, so a sample is re-derived from faces.0.csv first and the run refuses
if any of it disagrees. Wrong centroids would put the wrong names on videos.

WHAT IT WRITES (only with --apply)

  FACE-CLUSTERS-VIDEO.csv  one row per video face, with the frame it came from,
                           written to .tmp and renamed (learning 42)
  cluster tags             (hash, cluster, cN, faces-video), for every cluster
                           with at least two faces across photographs and video

No embedding file is written beside it. The embeddings already live in
faces.video.csv, in the row that describes each face, and anything that needs
them joins on (image, face_index) - a second copy matched by position is the
thing learning 45 says not to build.

It refuses to tag a second time. New cluster ids depend on the whole set of
video faces, so tagging again after more frames arrived would write different
ids for the same people into a store that is append-only and cannot take them
back.
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import io
import os
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
HERE = os.path.dirname(os.path.abspath(__file__))


from cluster_faces import DIM, check_alignment, cluster          # noqa: E402

ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
CACHE = r"D:\_PhotoAudit\face-emb.npy"
PHOTO_FACES = r"D:\_enrichment\faces.0.csv"
FACES = r"D:\_enrichment\faces.video.csv"
OUT = r"D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv"
MERGES = r"D:\_PhotoAudit\CLUSTER-MERGES.csv"
STORE = r"D:\_enrichment"
DB = r"D:\_PhotoAudit\library.db"


def iter_csv(p: str):
    """Streamed. content_tags.csv is 1.4 million rows on a machine that kills
    jobs under memory pressure (learning 9)."""
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        yield from csv.DictReader(f)


def read_csv(p: str) -> list[dict]:
    return list(iter_csv(p))


def face_rows(p: str) -> list[dict]:
    r"""Usable face rows. The guard and the conversion must read the SAME value.

    This tested `(face_index or "-1")` - so an EMPTY face_index defaulted to
    "-1", passed `.isdigit()`, and then crashed on `int(r["face_index"])`,
    which reads the raw "" the guard had just substituted away. 20 rows in
    faces.video.csv carry an empty face_index beside a 40-character hash and a
    score in the bbox column - a run killed mid-write, the shape of learning
    45 - and every one of them takes this function down.

    A row is skipped when its own value is not a usable index, and the value
    checked is the value used.
    """
    out = []
    for r in iter_csv(p):
        fi = (r.get("face_index") or "").strip()
        if not r.get("emb") or not fi.lstrip("-").isdigit() or int(fi) < 0:
            continue
        out.append(r)
    return out


def decode(emb: str):
    import numpy as np
    return np.frombuffer(base64.b64decode(emb), dtype=np.float16).astype(np.float32)


def verify(a, C, k: int) -> int:
    """Re-derive a sample of the written assignment. 0 right, 1 wrong, 2 not yet.

    Recomputes each sampled face's match against the frozen clusters from its
    own embedding in faces.video.csv, and checks the file covers every face
    detected - a file missing half the faces is well-formed and wrong
    (learning 33)."""
    import numpy as np
    if not os.path.exists(a.out):
        print("verify: no assignment written yet")
        return 2
    rows = read_csv(a.out)
    src = {(r["image"], r["face_index"]): r["emb"] for r in face_rows(a.faces)}
    if len(rows) != len(src):
        print("verify: {:,} assignments for {:,} detected faces".format(len(rows), len(src)))
        return 1
    if not rows:
        print("verify: an assignment file with no rows")
        return 1
    bad = checked = 0
    for i in range(0, len(rows), max(1, len(rows) // a.sample)):
        r = rows[i]
        emb = src.get((r["image"], r["face_index"]))
        if emb is None:
            bad += 1
            print("  {} face {}  not in {}".format(r["image"][:20], r["face_index"], a.faces))
            continue
        v = decode(emb)
        sims = C @ v
        j = int(sims.argmax())
        cid = int(r["cluster"][1:])
        joined = float(sims[j]) >= a.threshold
        ok = (cid == j) if joined else (cid >= k)
        checked += 1
        if not ok:
            bad += 1
            print("  row {}  written c{}, re-derived {}".format(
                i, cid, "c{}".format(j) if joined else "a new cluster"))
    print("verify: re-derived {} of {:,} assignments, {} wrong".format(
        checked, len(rows), bad))
    return 1 if bad else 0


def verify_db(a) -> int:
    """Did named people found in video frames reach library.db? 0/1/2 as above.

    Checked against photo_people, the table a question is actually answered
    from, for faces whose cluster Krish named directly."""
    import sqlite3
    if not os.path.exists(a.out):
        print("verify-db: no assignment written yet")
        return 2
    if not os.path.exists(a.db):
        print("verify-db: no database at {}".format(a.db))
        return 1
    named = {}
    for r in iter_csv(os.path.join(a.store, "answers.csv")):
        if r.get("scope") == "cluster":
            if r.get("field") == "person":
                named[r["target"]] = r["value"]
            elif r["target"] in named:
                del named[r["target"]]       # a later non-name answer supersedes
    rows = [r for r in iter_csv(a.out) if r["cluster"] in named]
    if not rows:
        print("verify-db: no video face is in a directly named cluster")
        return 1
    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")), uri=True)
    try:
        bad = checked = 0
        for r in rows[::max(1, len(rows) // a.sample)]:
            hit = db.execute("SELECT 1 FROM photo_people WHERE hash = ? AND person = ?",
                             (r["hash"], named[r["cluster"]])).fetchone()
            checked += 1
            if not hit:
                bad += 1
                print("  {}  {} not on the video in library.db".format(
                    r["hash"][:12], named[r["cluster"]]))
    finally:
        db.close()
    print("verify-db: {} named video faces checked, {} missing".format(checked, bad))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assign", default=ASSIGN)
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--photo-faces", default=PHOTO_FACES)
    ap.add_argument("--faces", default=FACES)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--merges", default=MERGES)
    ap.add_argument("--store", default=STORE)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--min-score", type=float, default=0.60)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="re-derive a sample of the written assignment and exit")
    ap.add_argument("--verify-db", action="store_true",
                    help="check named video faces reached library.db and exit")
    ap.add_argument("--sample", type=int, default=40)
    a = ap.parse_args()

    if a.verify_db:
        return verify_db(a)

    import numpy as np

    for p in (a.assign, a.photo_faces, a.faces):
        if not os.path.exists(p):
            print("STOPPING: {} does not exist".format(p))
            return 1

    # CENTROIDS BY KEY, NOT BY POSITION.
    #
    # This built them from face-emb.npy, a cache paired with FACE-CLUSTERS.csv
    # by ROW NUMBER, and guarded it with check_alignment because that pairing
    # is learning 45 exactly: a positional cache drifted once until 11,347 of
    # 11,611 vectors described the wrong photograph while every row count
    # agreed. The cache does not exist on this machine, so the tool could not
    # run at all - `--verify` stopped on the missing file and its test had been
    # failing on that rather than on anything it checks.
    #
    # Rebuilding the cache would rebuild the hazard. Learning 45's own durable
    # fix is "not to pair by position at all - put the payload in the row that
    # describes it", and faces.0.csv already does: every embedding sits in the
    # row carrying its (hash, face_index). Joined on that key there is no
    # positional artefact to drift and nothing to sample-check, and a frozen
    # face that cannot be found REFUSES the run, because a centroid built from
    # a partial cluster is a wrong centroid.
    photo = read_csv(a.assign)
    cluster_of = {(r["hash"], str(r["face_index"])): int(r["cluster"][1:])
                  for r in photo}
    kmax = max(cluster_of.values()) + 1
    S = np.zeros((kmax, DIM), dtype=np.float32)
    got = np.zeros(kmax, dtype=np.int64)
    for r in iter_csv(a.photo_faces):
        fi = r.get("face_index") or "-1"
        if not r.get("emb") or not fi.lstrip("-").isdigit() or int(fi) < 0:
            continue
        c = cluster_of.get((r["hash"], fi))
        if c is not None:
            S[c] += decode(r["emb"])
            got[c] += 1
    if int(got.sum()) != len(cluster_of):
        print("STOPPING: {:,} of {:,} frozen faces were not found in {} by "
              "(hash, face_index). A centroid built from a partial cluster is "
              "a wrong centroid, and it would put the wrong names on videos."
              .format(len(cluster_of) - int(got.sum()), len(cluster_of),
                      os.path.basename(a.photo_faces)))
        return 1
    print("frozen centroids joined from {} by key - every face found".format(
        os.path.basename(a.photo_faces)))

    ids = np.array([int(r["cluster"][1:]) for r in photo], dtype=np.int64)

    # THE NEW-ID FLOOR CLEARS EVERY FILE THAT HANDS ONE OUT, INCLUDING THIS
    # TOOL'S OWN PREVIOUS OUTPUT. Taking it from FACE-CLUSTERS.csv alone is the
    # mistake assign_new_faces.py made on 2026-09-23: it numbered 6,970 new
    # photograph clusters from the photograph maximum while 15,326 video
    # clusters already occupied c44284-c59609, so one id named two different
    # people and six of them already carried an answer. The same shape is
    # available here in reverse - a re-run whose previous video ids sit above
    # the photograph maximum would collide with itself - so the floor is a
    # maximum over both files rather than over the one this run happens to read.
    # TWO DIFFERENT NUMBERS, AND CONFLATING THEM BREAKS --verify.
    #
    # `k` was doing both jobs: the size of the centroid array AND the base for
    # new ids. Widening it to clear this tool's own previous output added rows
    # to C that no frozen face occupies, so they are zero vectors that never
    # match - and --verify, re-deriving the assignment, then called every face
    # that had been given one of those ids "a new cluster" and reported 3 of 5
    # assignments wrong on an assignment that was correct.
    #
    # The centroid space is what the FROZEN photograph clusters occupy. The
    # new-id base is the first id no file has handed out. They are separate.
    k = kmax                                     # centroid space
    prev = -1
    if os.path.exists(a.out):
        for r in iter_csv(a.out):
            c = (r.get("cluster") or "")
            if c[1:].isdigit():
                prev = max(prev, int(c[1:]))
    new_base = max(int(ids.max()), prev) + 1     # first free id
    photo_count = np.bincount(ids, minlength=k)
    nrm = np.linalg.norm(S, axis=1, keepdims=True)
    C = S / np.where(nrm > 0, nrm, 1.0)          # empty ids stay zero: never match
    del S
    print("frozen clusters: {:,} (ids c0-c{}), from {:,} photograph faces".format(
        int((photo_count > 0).sum()), k - 1, len(photo)))

    if a.verify:
        return verify(a, C, k)

    vids = face_rows(a.faces)
    if not vids:
        print("STOPPING: no video faces in {}".format(a.faces))
        return 1
    V = np.empty((len(vids), DIM), dtype=np.float32)
    for i, r in enumerate(vids):
        V[i] = decode(r["emb"])
    print("video faces: {:,} in {:,} frames of {:,} videos".format(
        len(vids), len({r["image"] for r in vids}), len({r["hash"] for r in vids})))

    # 1. join a frozen cluster where the centroid matches
    label = np.full(len(vids), -1, dtype=np.int64)
    CH = 256                                     # 256 x 44k float32 is ~45 MB
    for s in range(0, len(vids), CH):
        sims = V[s:s + CH] @ C.T
        j = sims.argmax(axis=1)
        best = sims[np.arange(len(j)), j]
        hit = best >= a.threshold
        part = label[s:s + CH]
        part[hit] = j[hit]
    matched = int((label >= 0).sum())

    # 2. everyone else clusters among themselves, numbered after the frozen ids
    miss = np.where(label < 0)[0]
    new_k = 0
    if len(miss):
        score = np.array([float(vids[i]["det_score"]) for i in miss],
                         dtype=np.float32)
        good = np.where(score >= a.min_score)[0]
        rest = np.where(score < a.min_score)[0]
        order = (list(good[np.argsort(-score[good])]) +
                 list(rest[np.argsort(-score[rest])]))
        sub, new_k = cluster(V[miss], order, a.threshold, say=lambda m: None)
        label[miss] = sub.astype(np.int64) + new_base
    del V

    total = collections.Counter(label.tolist())
    for c, n in enumerate(photo_count.tolist()):
        if n:
            total[c] += n

    # what it buys, in the terms that matter: named people found in video
    named = {}
    for r in iter_csv(os.path.join(a.store, "answers.csv")):
        if r.get("scope") == "cluster" and r.get("field") == "person":
            named[r["target"]] = r["value"]
    if os.path.exists(a.merges):
        for r in iter_csv(a.merges):
            if r.get("person") and r["cluster"] not in named:
                named[r["cluster"]] = r["person"]
    by_video = collections.defaultdict(set)
    for i, r in enumerate(vids):
        who = named.get("c{}".format(label[i]))
        if who:
            by_video[r["hash"]].add(who)

    print()
    print("joined an existing cluster : {:,} faces ({:.0f}%)".format(
        matched, 100.0 * matched / len(vids)))
    print("new clusters, video only   : {:,} (from {:,} faces)".format(
        new_k, len(miss)))
    print("videos with a NAMED person : {:,}".format(len(by_video)))
    top = collections.Counter(p for s in by_video.values() for p in s)
    print("  most seen: " + ", ".join(
        "{} {:,}".format(p, n) for p, n in top.most_common(8)))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    tags_csv = os.path.join(a.store, "content_tags.csv")
    have = set()
    already = 0
    if os.path.exists(tags_csv):
        for r in iter_csv(tags_csv):
            if r.get("tag") == "cluster":
                have.add((r["hash"], r["value"]))
                if r.get("source") == "faces-video":
                    already += 1
    if already:
        print()
        print("REFUSING: the store already holds {:,} faces-video cluster tags.".format(
            already))
        print("New-cluster ids depend on the whole set of video faces, so a second")
        print("run would tag the same people under different ids, permanently.")
        return 1

    tmp = a.out + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "image", "face_index", "cluster", "det_score", "bbox",
                    "how"])
        for i, r in enumerate(vids):
            w.writerow([r["hash"], r["image"], r["face_index"],
                        "c{}".format(label[i]), r["det_score"], r["bbox"],
                        "joined" if label[i] < new_base else "new"])
    os.replace(tmp, a.out)
    print()
    print("wrote {}".format(a.out))

    best = {}
    for i, r in enumerate(vids):
        c = int(label[i])
        if total[c] < 2:                         # a cluster of one is not a person
            continue
        key = (r["hash"], "c{}".format(c))
        if key in have:
            continue
        best[key] = max(best.get(key, 0.0), float(r["det_score"]))
    from store import Store
    n = Store(a.store).tag_many(
        [(h, "cluster", c, "faces-video", s) for (h, c), s in sorted(best.items())])
    print("wrote {:,} cluster tags (source faces-video). Rebuild library.db to see "
          "named people on the videos.".format(n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
