r"""Put video faces into the clusters Krish has already named. Never renumber.

    python assign_video_faces.py             # report, write nothing
    python assign_video_faces.py --apply

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

WHAT IT WRITES (only with --apply)

  FACE-CLUSTERS-VIDEO.csv  one row per video face, with the frame it came from
  face-emb-video.npy       the embeddings in the same order, for merge_clusters
  cluster tags             (hash, cluster, cN, faces-video), for every cluster
                           with at least two faces across photographs and video

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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "engine"))

from cluster_faces import DIM, cluster                           # noqa: E402

ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
CACHE = r"D:\_PhotoAudit\face-emb.npy"
FACES = r"D:\_enrichment\faces.video.csv"
OUT = r"D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv"
OUT_EMB = r"D:\_PhotoAudit\face-emb-video.npy"
MERGES = r"D:\_PhotoAudit\CLUSTER-MERGES.csv"
STORE = r"D:\_enrichment"


def read_csv(p: str) -> list[dict]:
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def face_rows(p: str) -> list[dict]:
    return [r for r in read_csv(p)
            if r.get("emb") and (r.get("face_index") or "-1").lstrip("-").isdigit()
            and int(r["face_index"]) >= 0]


def verify(a, C, k: int) -> int:
    """Re-derive a sample of written assignments. 0 right, 1 wrong, 2 can't tell.

    Two things are checked, because either alone passes a broken run: that each
    stored embedding is still the one faces.video.csv holds for that frame and
    face (the position-drift that corrupted 11,000 photographs on 2026-09-13),
    and that recomputing the match against the frozen clusters gives the cluster
    that was written."""
    import numpy as np
    if not (os.path.exists(a.out) and os.path.exists(a.out_emb)):
        print("verify: no assignment written yet")
        return 2
    rows = read_csv(a.out)
    V = np.load(a.out_emb)
    if len(rows) != V.shape[0]:
        print("verify: {:,} rows but {:,} embeddings - misaligned".format(
            len(rows), V.shape[0]))
        return 1
    if not rows:
        return 2
    src = {(r["image"], r["face_index"]): r["emb"] for r in face_rows(a.faces)}
    bad = checked = 0
    for i in range(0, len(rows), max(1, len(rows) // a.sample)):
        r = rows[i]
        emb = src.get((r["image"], r["face_index"]))
        if emb is None:
            bad += 1
            print("  {} face {}  not in {}".format(r["image"][:20], r["face_index"], a.faces))
            continue
        v = np.frombuffer(base64.b64decode(emb), dtype=np.float16).astype(np.float32)
        if float(np.dot(v, V[i])) < 0.99:
            bad += 1
            print("  row {}  stored embedding belongs to a different face".format(i))
            continue
        sims = C @ V[i]
        j = int(sims.argmax())
        cid = int(r["cluster"][1:])
        ok = (cid == j) if float(sims[j]) >= a.threshold else (cid >= k)
        checked += 1
        if not ok:
            bad += 1
            print("  row {}  written c{}, re-derived {}".format(
                i, cid, "c{}".format(j) if float(sims[j]) >= a.threshold else "a new cluster"))
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
    named = {}
    for r in read_csv(os.path.join(a.store, "answers.csv")):
        if r.get("scope") == "cluster":
            if r.get("field") == "person":
                named[r["target"]] = r["value"]
            elif r["target"] in named:
                del named[r["target"]]       # a later non-name answer supersedes
    rows = [r for r in read_csv(a.out) if r["cluster"] in named]
    if not rows:
        print("verify-db: no video face is in a directly named cluster")
        return 2
    db = sqlite3.connect("file:{}?mode=ro".format(
        os.path.join(os.path.dirname(a.out), "library.db").replace("\\", "/")), uri=True)
    bad = checked = 0
    for r in rows[::max(1, len(rows) // a.sample)]:
        hit = db.execute("SELECT 1 FROM photo_people WHERE hash = ? AND person = ?",
                         (r["hash"], named[r["cluster"]])).fetchone()
        checked += 1
        if not hit:
            bad += 1
            print("  {}  {} not on the video in library.db".format(
                r["hash"][:12], named[r["cluster"]]))
    print("verify-db: {} named video faces checked, {} missing".format(checked, bad))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assign", default=ASSIGN)
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--faces", default=FACES)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--out-emb", default=OUT_EMB)
    ap.add_argument("--merges", default=MERGES)
    ap.add_argument("--store", default=STORE)
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

    for p in (a.assign, a.cache, a.faces):
        if not os.path.exists(p):
            print("STOPPING: {} does not exist".format(p))
            return 1

    photo = read_csv(a.assign)
    E = np.load(a.cache)
    if len(photo) != E.shape[0]:
        print("STOPPING: {} rows in {} but {} embeddings in {} - they must "
              "describe the same faces in the same order".format(
                  len(photo), a.assign, E.shape[0], a.cache))
        return 1

    ids = np.array([int(r["cluster"][1:]) for r in photo], dtype=np.int64)
    k = int(ids.max()) + 1
    S = np.zeros((k, DIM), dtype=np.float32)
    np.add.at(S, ids, E)
    photo_count = np.bincount(ids, minlength=k)
    nrm = np.linalg.norm(S, axis=1, keepdims=True)
    C = S / np.where(nrm > 0, nrm, 1.0)          # empty ids stay zero: never match
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
        V[i] = np.frombuffer(base64.b64decode(r["emb"]), dtype=np.float16)
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
        label[miss] = sub.astype(np.int64) + k

    total = collections.Counter(label.tolist())
    for c, n in enumerate(photo_count.tolist()):
        if n:
            total[c] += n

    # what it buys, in the terms that matter: named people found in video
    named = {}
    for r in read_csv(os.path.join(a.store, "answers.csv")):
        if r.get("scope") == "cluster" and r.get("field") == "person":
            named[r["target"]] = r["value"]
    if os.path.exists(a.merges):
        for r in read_csv(a.merges):
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
    for r in read_csv(tags_csv):
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

    with io.open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "image", "face_index", "cluster", "det_score", "bbox",
                    "how"])
        for i, r in enumerate(vids):
            w.writerow([r["hash"], r["image"], r["face_index"],
                        "c{}".format(label[i]), r["det_score"], r["bbox"],
                        "joined" if label[i] < k else "new"])
    np.save(a.out_emb, V)
    print()
    print("wrote {} and {}".format(a.out, a.out_emb))

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
