r"""Merge clusters that are the same person, so nobody is asked eleven times.

    python merge_clusters.py                # report, write nothing
    python merge_clusters.py --apply

WHY MERGING IS SAFE AT THE CLUSTER LEVEL WHEN IT IS NOT AT THE FACE LEVEL

Faces were clustered at a cautious 0.55 because ONE face is noisy - a bad angle,
motion blur, half a face behind someone's shoulder. That caution was right and it
fragmented people: Krish named eleven separate clusters "Krish" and five
"Bharti", so 53 rows were really 28 people.

A cluster CENTROID is an average of hundreds of faces, and averages separate far
more cleanly than samples. Measured against Krish's own 53 labels:

    same person, different clusters : median 0.790   p25 0.714
    different people                : median 0.044   p95 0.243   max 0.639

Those distributions barely touch. The worst different-people pair in the whole
set is Shilu against Bharti at 0.639, which is a family resemblance and is
exactly what the margin exists for.

THE GROUND TRUTH IS USED AS A TEST, NOT AS A SUGGESTION

Every merge is checked against the names already given: if a proposed group
contains two clusters Krish called different people, that is a FAILED merge and
the run stops rather than quietly producing a group labelled with whichever name
it saw first. The threshold is only trusted because it survives that check.

WHAT A PROPAGATED NAME IS, AND IS NOT

If a group contains one named cluster and four unnamed ones, the name is written
onto the others as a DERIVED tag - source "cluster-merge", never "human". It is
an inference from a measurement, it ranks below anything Krish says, and a later
answer from him overrides it without argument. The answers journal is not
touched: no machine writes to it, which is the one rule the whole design rests
on.

NO POSITIONAL CACHE (learning 45)

This used to read `face-emb.npy`, a cache paired with FACE-CLUSTERS.csv BY ROW
NUMBER and guarded by a re-derived sample. That cache does not exist on the
library machine, so from the day it went missing every run of this script died
on np.load - and both nightly chains carry on past a non-zero merge, so names
silently stopped reaching sibling clusters (found 2026-10-16, on the first app
sync since the cloud took over). The two assigners had already moved to the
durable fix, and this does the same: every embedding is read from the
`faces.0.csv` row that carries its (hash, face_index), joined to the
assignment by that key. There is no file to drift out of step and nothing to
re-derive. A frozen face the photograph file cannot produce stops the run,
because a centroid built from a partial cluster is a wrong centroid, and a
wrong centroid merges strangers while passing the name test.
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import io
import itertools
import os
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
HERE = os.path.dirname(os.path.abspath(__file__))


ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
FACES = r"D:\_enrichment\faces.0.csv"
ANSWERS = r"D:\_enrichment\answers.csv"
MERGES = r"D:\_PhotoAudit\CLUSTER-MERGES.csv"


def decode(emb: str):
    import numpy as np
    return np.frombuffer(base64.b64decode(emb), dtype=np.float16).astype(np.float32)


def photo_sums(assign: str, faces: str, dim: int):
    """Every frozen photograph face summed into its cluster, joined by KEY.

    -> (sums, count, byc, faces_found, problem). `problem` is None, or the
    reason the run must stop: a frozen face the photograph file cannot produce,
    or one key assigned to two clusters. Never paired by position.
    """
    import numpy as np
    cluster_of, byc, clash = {}, collections.defaultdict(set), []
    for r in csv.DictReader(io.open(assign, encoding="utf-8", errors="replace", newline="")):
        key = (r["hash"], str(r.get("face_index") or ""))
        if key in cluster_of and cluster_of[key] != r["cluster"]:
            clash.append(key)
        cluster_of[key] = r["cluster"]
        byc[r["cluster"]].add(r["hash"])
    if clash:
        return None, None, byc, 0, ("{:,} face(s) assigned to two different clusters, "
                                    "e.g. {}".format(len(clash), clash[0]))
    sums = collections.defaultdict(lambda: np.zeros(dim, dtype=np.float32))
    count, found = collections.Counter(), set()
    for r in csv.DictReader(io.open(faces, encoding="utf-8", errors="replace", newline="")):
        fi = r.get("face_index") or "-1"
        if not r.get("emb") or not fi.lstrip("-").isdigit() or int(fi) < 0:
            continue
        key = (r["hash"], fi)
        c = cluster_of.get(key)
        if c is None or key in found:       # not frozen, or the same face twice
            continue
        found.add(key)
        sums[c] += decode(r["emb"])
        count[c] += 1
    missing = len(cluster_of) - len(found)
    if missing:
        return sums, count, byc, len(found), (
            "{:,} of {:,} frozen faces were not found in {} by (hash, face_index). "
            "A centroid built from a partial cluster is a wrong centroid.".format(
                missing, len(cluster_of), os.path.basename(faces)))
    return sums, count, byc, len(found), None


def find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assign", default=ASSIGN)
    ap.add_argument("--photo-faces", default=FACES,
                    help="photograph embeddings, joined on (hash, face_index)")
    ap.add_argument("--video-assign", default=r"D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv",
                    help="video faces from assign_video_faces.py; skipped if absent")
    ap.add_argument("--video-faces", default=r"D:\_enrichment\faces.video.csv",
                    help="their embeddings, joined on (image, face_index)")
    ap.add_argument("--answers", default=ANSWERS)
    ap.add_argument("--out", default=MERGES)
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--threshold", type=float, default=0.70)
    ap.add_argument("--min-faces", type=int, default=3)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    import numpy as np
    from cluster_faces import DIM
    for path in (a.assign, a.photo_faces):
        if not os.path.exists(path):
            print("STOPPING: {} does not exist".format(path))
            return 1
    sums, count, byc, nphoto, problem = photo_sums(a.assign, a.photo_faces, DIM)
    if problem:
        print("STOPPING: " + problem)
        return 1
    print("every frozen photograph face found in {} by (hash, face_index): {:,}".format(
        os.path.basename(a.photo_faces), nphoto))

    # VIDEO FACES, joined on (image, face_index) and NOT by position: each
    # embedding stays in the row that describes it, so there is no second file
    # to drift out of step (learning 45). Without them a person who appears only
    # on video never merges with their photograph cluster, and a name never
    # reaches a video face sitting in an unnamed sibling cluster.
    nvideo = 0
    if os.path.exists(a.video_assign) and os.path.exists(a.video_faces):
        cluster_of = {}
        for r in csv.DictReader(io.open(a.video_assign, encoding="utf-8",
                                        errors="replace", newline="")):
            cluster_of[(r["image"], r["face_index"])] = r["cluster"]
            byc[r["cluster"]].add(r["hash"])
        for r in csv.DictReader(io.open(a.video_faces, encoding="utf-8",
                                        errors="replace", newline="")):
            c = cluster_of.get((r.get("image"), r.get("face_index")))
            if not c or not r.get("emb"):
                continue
            sums[c] += np.frombuffer(base64.b64decode(r["emb"]),
                                     dtype=np.float16).astype(np.float32)
            count[c] += 1
            nvideo += 1
        if nvideo != len(cluster_of):
            print("STOPPING: {:,} video assignments but {:,} of their embeddings "
                  "were found - a join that silently drops faces would merge on "
                  "partial centroids".format(len(cluster_of), nvideo))
            return 1
        print("video faces joined in: {:,}".format(nvideo))
    else:
        print("no video faces yet - photographs only")

    clusters = [c for c, n in count.items() if n >= a.min_faces]
    print("clusters with {}+ faces: {:,}   (from {:,} photograph and {:,} video "
          "faces)".format(a.min_faces, len(clusters), nphoto, nvideo))

    C = np.zeros((len(clusters), DIM), dtype=np.float32)
    for n, c in enumerate(clusters):
        v = sums[c] / max(count[c], 1)
        C[n] = v / max(float(np.linalg.norm(v)), 1e-9)

    names = {}
    if os.path.exists(a.answers):
        for r in csv.DictReader(io.open(a.answers, encoding="utf-8", newline="")):
            if r.get("field") == "person":
                names[r["target"]] = r["value"]
    print("clusters already named by a human: {}".format(
        sum(1 for c in clusters if c in names)))

    # GREEDY AGAINST THE GROUP CENTROID, NOT TRANSITIVE UNION-FIND.
    #
    # Union-find merges A with C whenever A~B and B~C, even if A and C are
    # nothing alike. At 0.60 that chained Bharti + Lily + Mami + Shilu + Vibha
    # into a single group - five people, presumably a family resemblance walking
    # the chain one link at a time. One bad link collapses everybody it touches,
    # and the failure is silent.
    #
    # So a cluster joins a group only if it is above threshold against that
    # GROUP's running centroid, which every existing member is already close to.
    # Chaining cannot happen: the thing being compared against moves toward the
    # members, so a drifting candidate stops matching.
    sizes_by_c = {c: count[c] for c in clusters}
    biggest = sorted(range(len(clusters)), key=lambda n: -sizes_by_c[clusters[n]])
    gcent = np.zeros_like(C)
    gsum = np.zeros_like(C)
    gmembers = []
    pairs = 0
    for n in biggest:
        v = C[n]
        if gmembers:
            sims = gcent[:len(gmembers)] @ v
            j = int(np.argmax(sims))
            if sims[j] >= a.threshold:
                gmembers[j].append(clusters[n])
                gsum[j] += v * sizes_by_c[clusters[n]]
                nr = float(np.linalg.norm(gsum[j]))
                gcent[j] = gsum[j] / (nr if nr else 1.0)
                pairs += 1
                continue
        k = len(gmembers)
        gmembers.append([clusters[n]])
        gsum[k] = v * sizes_by_c[clusters[n]]
        gcent[k] = v

    groups = {m[0]: m for m in gmembers}
    multi = {g: v for g, v in groups.items() if len(v) > 1}
    print("threshold {:.2f}: {:,} merges, {:,} groups of more than one".format(
        a.threshold, pairs, len(multi)))

    # THE TEST: no group may hold two clusters a human called different people
    conflicts = []
    for g, members in multi.items():
        named = {names[c] for c in members if c in names}
        if len(named) > 1:
            conflicts.append((g, sorted(named), members))
    if conflicts:
        print()
        print("REFUSING TO MERGE - {} group(s) would put different people "
              "together:".format(len(conflicts)))
        for g, named, members in conflicts[:8]:
            print("   {} <- {}".format(" + ".join(named), ", ".join(members[:6])))
        print()
        print("Lower --threshold until this is empty. A merge that survives this")
        print("check is safe; one that does not would label somebody with another")
        print("person's name and look deliberate afterwards.")
        return 1
    print("no group mixes two differently-named people - the threshold holds")

    # what it buys
    named_groups = [g for g, v in groups.items() if any(c in names for c in v)]
    gain = sum(len([c for c in groups[g] if c not in names]) for g in named_groups)
    print()
    print("clusters before : {:,}".format(len(clusters)))
    print("groups after    : {:,}".format(len(groups)))
    print("unnamed clusters that inherit a name from a named sibling: {:,}".format(gain))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return 0

    # .tmp and rename: people_sheet and assign_video_faces read this file, and a
    # reader must see the old one or the new one, never a prefix (learning 42)
    tmp = a.out + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cluster", "group", "person", "source"])
        for g, members in groups.items():
            named = {names[c] for c in members if c in names}
            person = sorted(named)[0] if named else ""
            for c in members:
                src = "human" if c in names else ("cluster-merge" if person else "")
                w.writerow([c, g, person if src else "", src])
    os.replace(tmp, a.out)
    print()
    print("wrote {}".format(a.out))

    # propagate as DERIVED tags. Never into the answers journal.
    from store import Store
    st = Store(a.store)
    out = []
    n = 0
    for g, members in groups.items():
        named = {names[c] for c in members if c in names}
        if len(named) != 1:
            continue
        person = next(iter(named))
        for c in members:
            if c in names:
                continue
            for h in byc[c]:
                out.append((h, "person", person, "cluster-merge", 0.9))
                n += 1
    # The store is append-only, and this runs again every time new names arrive.
    # Without this, each re-run re-appends every tag the previous runs wrote.
    have = set()
    tags_csv = os.path.join(a.store, "content_tags.csv")
    if os.path.exists(tags_csv):
        for r in csv.DictReader(io.open(tags_csv, encoding="utf-8",
                                        errors="replace", newline="")):
            if r.get("source") == "cluster-merge" and r.get("tag") == "person":
                have.add((r["hash"], r["value"]))
    fresh = []
    for t in out:
        if (t[0], t[2]) not in have:
            have.add((t[0], t[2]))
            fresh.append(t)
    if fresh:
        st.tag_many(fresh)
    print("propagated {:,} derived person tags, {:,} of them new (source "
          "'cluster-merge', which ranks BELOW anything Krish says)".format(
              n, len(fresh)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
