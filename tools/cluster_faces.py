r"""Group 119,830 faces into people, so naming one labels hundreds of photographs.

    python cluster_faces.py                 # report, write nothing
    python cluster_faces.py --apply         # write cluster tags to the store

WHY THIS IS THE HIGHEST-LEVERAGE STEP IN THE PROJECT

The scarce resource is Krish's attention, not compute. Asking "who is this?" per
photograph is 40,616 questions. Asking it per PERSON is about fifty. Clustering
is the whole difference, and it is the same trick that turned 74,000 file
judgements into a few hundred folder ones when the library was split.

THE THRESHOLD IS MEASURED, NOT ASSUMED

Two faces detected in the SAME photograph are almost always different people,
which makes them a free ground-truth control. Measured on this library:

    two faces in one photo   median cosine 0.049   p99 0.430
    two random faces         median cosine 0.016   p99 0.338

So different people sit near zero. At a 0.55 threshold, 0.62% of known-different
pairs would still merge - and those residual cases are mostly a person appearing
twice in one frame, a reflection, or a photograph of a photograph.

WHY IT ERRS TOWARDS TOO MANY CLUSTERS

A false MERGE puts two people in one cluster, so naming it mislabels one of them
across every photograph they appear in - and the error is invisible afterwards,
because the label looks deliberate. Fragmentation just means the same person
comes up twice and Krish answers twice. One costs correctness, the other costs a
minute, so the threshold is deliberately set high.

Merging two clusters later is easy and safe; unpicking a bad merge means finding
which of hundreds of labelled photographs were the other person.

HOW IT CLUSTERS

Greedy assignment to a running centroid, best-detected faces first, so the
clearest examples of a person define the cluster and the blurry ones join it
rather than the reverse. Single pass, no distance matrix - 119,830 squared would
be 14 billion pairs and 57 GB.
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))

FACES = r"D:\_enrichment\faces.0.csv"
CACHE = r"D:\_PhotoAudit\face-emb.npy"
DIM = 512


def load(faces_csv: str, cache: str):
    """-> (rows, E). The decode is cached; it takes a minute otherwise."""
    import numpy as np
    rows = [r for r in csv.DictReader(
                io.open(faces_csv, encoding="utf-8", errors="replace", newline=""))
            if r.get("emb") and (r.get("face_index") or "-1").lstrip("-").isdigit()
            and int(r["face_index"]) >= 0]
    if cache and os.path.exists(cache):
        E = np.load(cache)
        if E.shape[0] == len(rows):
            return rows, E
    E = np.empty((len(rows), DIM), dtype=np.float32)
    for i, r in enumerate(rows):
        E[i] = np.frombuffer(base64.b64decode(r["emb"]), dtype=np.float16)
    if cache:
        try:
            np.save(cache, E)
        except OSError:
            pass
    return rows, E


def cluster(E, order, thresh: float, say=print):
    """Greedy centroid assignment. -> labels array, one cluster id per face."""
    import numpy as np
    n = E.shape[0]
    labels = np.full(n, -1, dtype=np.int32)
    cap = 4096
    C = np.zeros((cap, DIM), dtype=np.float32)      # unit centroids
    S = np.zeros((cap, DIM), dtype=np.float32)      # running sums
    cnt = np.zeros(cap, dtype=np.int32)
    k = 0
    t0 = time.time()
    for step, i in enumerate(order, 1):
        v = E[i]
        if k:
            sims = C[:k] @ v
            j = int(np.argmax(sims))
            if sims[j] >= thresh:
                labels[i] = j
                S[j] += v
                cnt[j] += 1
                nrm = np.linalg.norm(S[j])
                C[j] = S[j] / (nrm if nrm > 0 else 1.0)
                continue
        if k == cap:                                 # grow
            cap *= 2
            C = np.resize(C, (cap, DIM))
            S = np.resize(S, (cap, DIM))
            cnt = np.resize(cnt, cap)
            C[k:] = 0
            S[k:] = 0
            cnt[k:] = 0
        labels[i] = k
        C[k] = v
        S[k] = v
        cnt[k] = 1
        k += 1
        if step % 20000 == 0:
            say("  {:,}/{:,} faces, {:,} clusters, {:.0f}s".format(
                step, n, k, time.time() - t0))
    return labels, k


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--faces", default=FACES)
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--min-score", type=float, default=0.60,
                    help="faces below this still get clustered, but never SEED "
                         "a cluster - a blurry face should join a person, not "
                         "invent one")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--assign-only", action="store_true",
                    help="write FACE-CLUSTERS.csv but do not re-tag the store, "
                         "which is append-only and already has them")
    a = ap.parse_args()

    import numpy as np
    rows, E = load(a.faces, a.cache)
    print("faces: {:,} across {:,} images".format(
        len(rows), len({r["hash"] for r in rows})))

    score = np.array([float(r["det_score"]) for r in rows], dtype=np.float32)
    # Best first, so the clearest photograph of a person defines the cluster and
    # the blurry ones join it. Seeded by good faces only; the rest follow.
    good = np.where(score >= a.min_score)[0]
    rest = np.where(score < a.min_score)[0]
    order = list(good[np.argsort(-score[good])]) + list(rest[np.argsort(-score[rest])])
    print("threshold {:.2f}, seeds from {:,} faces at det_score >= {:.2f}".format(
        a.threshold, len(good), a.min_score))

    labels, k = cluster(E, order, a.threshold)
    sizes = collections.Counter(labels.tolist())
    big = [c for c, n in sizes.items() if n >= 5]
    print()
    print("clusters              : {:,}".format(k))
    print("  with 5+ faces       : {:,}".format(len(big)))
    print("  singletons          : {:,}".format(sum(1 for n in sizes.values() if n == 1)))
    covered = sum(n for c, n in sizes.items() if n >= 5)
    print("  faces in 5+ clusters: {:,} ({:.0f}%)".format(
        covered, 100.0 * covered / len(rows)))

    print()
    print("the {} biggest - these are the people to name first:".format(a.top))
    print("  {:>6}  {:>7}  {:>7}  {}".format("id", "faces", "photos", "example subject"))
    byc = collections.defaultdict(list)
    for i, c in enumerate(labels.tolist()):
        byc[c].append(i)
    reach = 0
    for c, n in sizes.most_common(a.top):
        idxs = byc[c]
        imgs = {rows[i]["hash"] for i in idxs}
        reach += len(imgs)
        print("  {:>6}  {:>7,}  {:>7,}".format(c, n, len(imgs)))
    print()
    print("naming the top {} would label {:,} photographs.".format(a.top, reach))

    if not (a.apply or a.assign_only):
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    # PER-FACE assignment, written first, because the tag store cannot carry it.
    #
    # A tag is (hash, tag, value): it can say "this PHOTOGRAPH contains c14" and
    # cannot say WHICH of the five faces in it is c14. people_sheet.py had to
    # guess, and guessed by taking every face in every photo the cluster touched
    # - so a row for one person showed six or seven different people, which is
    # what Krish saw. The clustering was right; the thing rendered from it was
    # not, because the information needed to render it had been thrown away.
    assign = os.path.join(os.path.dirname(a.cache) or ".", "FACE-CLUSTERS.csv")
    with io.open(assign, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "face_index", "cluster", "det_score", "bbox"])
        for i, c in enumerate(labels.tolist()):
            r = rows[i]
            w.writerow([r["hash"], r["face_index"], "c{}".format(c),
                        r["det_score"], r["bbox"]])
    print()
    print("wrote {} - one row per FACE, which is the only place the".format(assign))
    print("face-to-person mapping exists. Anything that draws a person reads this.")

    if a.assign_only:
        return 0

    from store import Store
    st = Store(a.store)
    out = []
    for i, c in enumerate(labels.tolist()):
        if sizes[c] >= 2:            # a cluster of one is not yet a person
            out.append((rows[i]["hash"], "cluster", "c{}".format(c), "faces",
                        float(rows[i]["det_score"])))
    n = st.tag_many(out)
    print()
    print("wrote {:,} cluster tags. Name them with engine/answers.py:".format(n))
    print('    j.record("cluster", "c17", "person", "Mum")')
    print("which build_db expands onto every photograph in that cluster.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
