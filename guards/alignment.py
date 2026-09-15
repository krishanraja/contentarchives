"""Two artefacts paired by position must be proven to still line up.

Learning 45: faces.csv and a parallel faces.f16 were matched by row number. A
kill left one longer than the other, both were appended to on resume, and from
slot 754 onwards every embedding belonged to a different photograph. Row counts
agreed within buffering, every vector was a valid unit vector, and 11,347 of
11,611 were wrong. Only recomputing from the source could tell.

The durable fix is not to pair by position at all - put the payload in the row
that describes it. Where a positional cache already exists (face-emb.npy against
FACE-CLUSTERS.csv), check a sample against its source before trusting it.
"""

from __future__ import annotations

import base64
import csv
import io


def check_alignment(rows, E, faces_csv: str, sample: int = 24) -> list[str]:
    """Re-derive a sample of E from its source. -> problems; empty means aligned.

    rows[i] must carry "hash" and "face_index"; E[i] must be the float32 decode
    of the float16 embedding faces_csv holds for that (hash, face_index). Sampled
    across the start, middle and end, and streamed so only the sampled keys are
    held in memory.
    """
    import numpy as np
    n = len(rows)
    if n != E.shape[0]:
        return ["{:,} rows but {:,} embeddings".format(n, E.shape[0])]
    if n == 0:
        return ["no rows to check"]
    idx = sorted({0, n - 1} | {int(i * (n - 1) / max(sample - 1, 1))
                               for i in range(sample)})
    want = {(rows[i]["hash"], str(rows[i]["face_index"])): i for i in idx}
    found = {}
    with io.open(faces_csv, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            k = (r.get("hash"), str(r.get("face_index")))
            if k in want and r.get("emb"):
                found[k] = r["emb"]
    problems = []
    for k, i in sorted(want.items(), key=lambda kv: kv[1]):
        if k not in found:
            problems.append("row {:,} ({} face {}) is not in {}".format(
                i, k[0][:12], k[1], faces_csv))
            continue
        v = np.frombuffer(base64.b64decode(found[k]), dtype=np.float16).astype(np.float32)
        cos = float(np.dot(v, E[i]))
        if cos < 0.99:
            problems.append("row {:,} ({} face {}): cached embedding has cosine {:.3f} "
                            "with its source".format(i, k[0][:12], k[1], cos))
    return problems
