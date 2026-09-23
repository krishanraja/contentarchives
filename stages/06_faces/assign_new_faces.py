r"""Put newly ingested PHOTOGRAPH faces into the clusters Krish already named.

    python assign_new_faces.py              # report, write nothing
    python assign_new_faces.py --apply

WHY THIS EXISTS

`assign_video_faces.py` says it in its first line: "Never renumber." Cluster ids
are what the journal points at - "c14 = Krish" is recorded against c14 - and
`cluster_faces.py` numbers clusters in the order it meets them, seeded best
det_score first. Feed it 24,550 more faces and the order interleaves, every id
shifts, and all 1,609 human answers silently describe somebody else. Nothing
would show it had happened, because each answer would still land on a real
cluster. Stage 06's invariant is therefore absolute: **never re-run
`cluster_faces.py --apply`.**

That invariant had a hole. `assign_video_faces.py` exists for faces arriving
from VIDEO FRAMES, and nothing existed for faces arriving from new
PHOTOGRAPHS - which is what every ingest produces. After 2026-09-22 brought in
11,707 files and 24,550 new photograph faces, the only tool that would have
taken them was the one the invariant forbids.

So this is that tool, and it is `assign_video_faces.py`'s algorithm on the
photograph side: a new face joins the frozen cluster whose centroid it matches
at the same 0.55 the library was clustered at, and the faces that match nobody
are clustered among themselves, best-detected first, numbered after the highest
existing id. Naming one of those new clusters names everyone in it.

THE CENTROIDS ARE JOINED BY KEY, NOT BY POSITION

`assign_video_faces.py` builds them from `face-emb.npy`, a cache paired with
`FACE-CLUSTERS.csv` BY POSITION, and guards it with a re-derived sample because
that pairing is the exact shape of learning 45 - a positional cache drifted once
and 11,347 of 11,611 vectors described the wrong photograph while every row
count agreed.

That cache does not exist on this machine, and rebuilding one to consume it
would be rebuilding the hazard. Learning 45's own durable fix is "not to pair by
position at all - put the payload in the row that describes it", and
`faces.0.csv` already does: every embedding sits in the row carrying its
`(hash, face_index)`. So the centroids are joined on that key. There is no
positional artefact to drift, and no sample check is needed because nothing is
being taken on trust.

WHAT IT WRITES

Rows appended to `FACE-CLUSTERS.csv`, in its own columns, for faces that file
does not already carry. The existing rows are never rewritten - that is what
"frozen" means - and the file is copied aside before the append, because this
project has lost a record to a careless write before.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import os
import shutil
import sys
import time

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives

AUDIT = r"D:\_PhotoAudit"
STORE = r"D:\_enrichment"
ASSIGN = os.path.join(AUDIT, "FACE-CLUSTERS.csv")
VIDEO_ASSIGN = os.path.join(AUDIT, "FACE-CLUSTERS-VIDEO.csv")
FACES = os.path.join(STORE, "faces.0.csv")
DIM = 512


def read_csv(p):
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def decode(emb):
    import numpy as np
    return np.frombuffer(base64.b64decode(emb), dtype=np.float16).astype(np.float32)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assign", default=ASSIGN)
    ap.add_argument("--video-assign", default=VIDEO_ASSIGN,
                    help="the OTHER file that hands out cluster ids. A new "
                         "id must clear both or two different people share one.")
    ap.add_argument("--faces", default=FACES)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--min-score", type=float, default=0.60,
                    help="a face below this joins a person but never SEEDS a "
                         "new cluster - a blurry face should not invent one")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    import numpy as np

    for p in (a.assign, a.faces):
        if not os.path.exists(p):
            print("STOPPING: {} does not exist".format(p))
            return 1

    frozen = read_csv(a.assign)
    cluster_of = {(r["hash"], str(r["face_index"])): int(r["cluster"][1:])
                  for r in frozen}
    photo_max = max(cluster_of.values())

    # THE NEXT FREE ID MUST CLEAR EVERY FILE THAT HANDS ONE OUT, NOT JUST THIS
    # ONE. `assign_video_faces.py` numbers ITS new clusters after the highest
    # id in FACE-CLUSTERS.csv and writes them to a SEPARATE file, so the ids
    # above the photograph maximum are already taken - 15,326 of them, c44284
    # to c59609. Numbering from the photograph file alone put 6,970 new
    # photograph clusters straight on top of them on 2026-09-23, so c44588
    # named one group of faces in video and a different group in photographs,
    # and six of them already carried one of Krish's answers. An answer that
    # lands on two different people is the exact harm the frozen-id invariant
    # exists to prevent, arriving through the door built to honour it.
    video_max = -1
    if os.path.exists(a.video_assign):
        for r in csv.DictReader(io.open(a.video_assign, encoding="utf-8",
                                        errors="replace", newline="")):
            c = r.get("cluster") or ""
            if c[1:].isdigit():
                video_max = max(video_max, int(c[1:]))
    else:
        print("STOPPING: {} is missing. It hands out cluster ids too, and "
              "without reading it this cannot know which are free."
              .format(a.video_assign))
        return 1
    k = max(photo_max, video_max) + 1
    print("frozen assignment: {:,} faces, photograph ids up to c{}".format(
        len(cluster_of), photo_max))
    print("video assignment : ids up to c{}".format(video_max))
    print("new ids start at : c{}  (clear of both)".format(k))

    # One pass over faces.0.csv: every embedding is summed into its cluster by
    # KEY, and any row the frozen assignment does not name is kept as new work.
    S = np.zeros((k, DIM), dtype=np.float32)
    counts = np.zeros(k, dtype=np.int64)
    fresh = []
    for r in csv.DictReader(io.open(a.faces, encoding="utf-8", errors="replace",
                                    newline="")):
        fi = r.get("face_index") or "-1"
        if not r.get("emb") or not fi.lstrip("-").isdigit() or int(fi) < 0:
            continue
        c = cluster_of.get((r["hash"], fi))
        if c is None:
            fresh.append(r)
        else:
            S[c] += decode(r["emb"])
            counts[c] += 1
    seen = int(counts.sum())
    if seen != len(cluster_of):
        print("STOPPING: {:,} of {:,} frozen faces were not found in {} by key. "
              "A centroid built from a partial cluster is a wrong centroid."
              .format(len(cluster_of) - seen, len(cluster_of),
                      os.path.basename(a.faces)))
        return 1
    print("every frozen face found in {} by (hash, face_index)".format(
        os.path.basename(a.faces)))
    del cluster_of
    nrm = np.linalg.norm(S, axis=1, keepdims=True)
    C = S / np.where(nrm > 0, nrm, 1.0)          # empty ids stay zero: never match
    del S, frozen
    print("frozen clusters: {:,} of {:,} ids carry faces".format(
        int((counts > 0).sum()), k))

    if not fresh:
        print("no faces outside the frozen assignment - nothing to do")
        return 0
    print("faces not yet assigned: {:,} across {:,} photographs".format(
        len(fresh), len({r["hash"] for r in fresh})))

    V = np.empty((len(fresh), DIM), dtype=np.float32)
    for i, r in enumerate(fresh):
        V[i] = decode(r["emb"])
    V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

    # 1. join a frozen cluster where the centroid matches
    label = np.full(len(fresh), -1, dtype=np.int64)
    CH = 256
    for s in range(0, len(fresh), CH):
        sims = V[s:s + CH] @ C.T
        j = sims.argmax(axis=1)
        best = sims[np.arange(len(j)), j]
        hit = best >= a.threshold
        label[s:s + CH][hit] = j[hit]
    matched = int((label >= 0).sum())
    print("joined an existing cluster: {:,}  ({:.1f}%)".format(
        matched, 100.0 * matched / len(fresh)))

    # 2. everyone else clusters among themselves, numbered after the frozen ids
    miss = np.where(label < 0)[0]
    new_k = 0
    if len(miss):
        score = np.array([float(fresh[i]["det_score"] or 0) for i in miss],
                         dtype=np.float32)
        good = np.where(score >= a.min_score)[0]
        rest = np.where(score < a.min_score)[0]
        order = (list(good[np.argsort(-score[good])])
                 + list(rest[np.argsort(-score[rest])]))
        cap = 4096
        NC = np.zeros((cap, DIM), dtype=np.float32)
        NS = np.zeros((cap, DIM), dtype=np.float32)
        t0 = time.time()
        for step, oi in enumerate(order, 1):
            i = miss[oi]
            v = V[i]
            if new_k:
                sims = NC[:new_k] @ v
                j = int(np.argmax(sims))
                if sims[j] >= a.threshold:
                    label[i] = k + j
                    NS[j] += v
                    n2 = np.linalg.norm(NS[j])
                    NC[j] = NS[j] / (n2 if n2 > 0 else 1.0)
                    continue
            if score[oi] < a.min_score and new_k:
                # never SEEDS: a blurry face that matched nobody is left for the
                # sheet to show as its own row rather than inventing a person
                label[i] = k + new_k
                NS[new_k] = v
                NC[new_k] = v
                new_k += 1
                continue
            if new_k == cap:
                cap *= 2
                NC = np.resize(NC, (cap, DIM)); NS = np.resize(NS, (cap, DIM))
                NC[new_k:] = 0; NS[new_k:] = 0
            label[i] = k + new_k
            NC[new_k] = v
            NS[new_k] = v
            new_k += 1
            if step % 5000 == 0:
                print("  {:,}/{:,} unmatched, {:,} new clusters, {:.0f}s".format(
                    step, len(miss), new_k, time.time() - t0), flush=True)
    print("new clusters formed       : {:,}  (ids c{}-c{})".format(
        new_k, k, k + new_k - 1 if new_k else k))

    sizes = {}
    for i in range(len(fresh)):
        sizes[int(label[i])] = sizes.get(int(label[i]), 0) + 1
    big = sorted(((c, n) for c, n in sizes.items() if c >= k),
                 key=lambda x: -x[1])[:10]
    if big:
        print()
        print("  biggest NEW clusters - naming one names everyone in it:")
        for c, n in big:
            print("    c{:<8} {:>5,} faces".format(c, n))

    if not a.apply:
        print()
        print("REPORT ONLY - nothing written. Re-run with --apply.")
        return 0

    bak = a.assign + ".pre-assign-new"
    if not os.path.exists(bak):
        shutil.copy2(a.assign, bak)
        print()
        print("copied the frozen assignment aside -> {}".format(bak))
    with io.open(a.assign, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        for i, r in enumerate(fresh):
            w.writerow([r["hash"], r["face_index"], "c{}".format(int(label[i])),
                        r.get("det_score", ""), r.get("bbox", "")])
        fh.flush()
        os.fsync(fh.fileno())
    print("appended {:,} rows to {}".format(len(fresh), a.assign))
    print()
    print("Now: python stages/06_faces/backfill_cluster_tags.py --apply")
    print("     so no sheet can offer a row the store cannot hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
