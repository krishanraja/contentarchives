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
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))

ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
CACHE = r"D:\_PhotoAudit\face-emb.npy"
ANSWERS = r"D:\_enrichment\answers.csv"
MERGES = r"D:\_PhotoAudit\CLUSTER-MERGES.csv"


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
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--answers", default=ANSWERS)
    ap.add_argument("--out", default=MERGES)
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--threshold", type=float, default=0.70)
    ap.add_argument("--min-faces", type=int, default=3)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    import numpy as np
    E = np.load(a.cache)
    rows = list(csv.DictReader(io.open(a.assign, encoding="utf-8",
                                       errors="replace", newline="")))
    if len(rows) != E.shape[0]:
        print("assignment file and embedding cache disagree: {} vs {}".format(
            len(rows), E.shape[0]))
        return 1

    idxs = collections.defaultdict(list)
    for i, r in enumerate(rows):
        idxs[r["cluster"]].append(i)
    clusters = [c for c, v in idxs.items() if len(v) >= a.min_faces]
    print("clusters with {}+ faces: {:,}".format(a.min_faces, len(clusters)))

    C = np.zeros((len(clusters), E.shape[1]), dtype=np.float32)
    for n, c in enumerate(clusters):
        v = E[idxs[c]].mean(axis=0)
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
    sizes_by_c = {c: len(idxs[c]) for c in clusters}
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

    with io.open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cluster", "group", "person", "source"])
        for g, members in groups.items():
            named = {names[c] for c in members if c in names}
            person = sorted(named)[0] if named else ""
            for c in members:
                src = "human" if c in names else ("cluster-merge" if person else "")
                w.writerow([c, g, person if src else "", src])
    print()
    print("wrote {}".format(a.out))

    # propagate as DERIVED tags. Never into the answers journal.
    from store import Store
    st = Store(a.store)
    out = []
    byc = collections.defaultdict(set)
    for r in rows:
        byc[r["cluster"]].add(r["hash"])
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
