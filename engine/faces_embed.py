r"""Detect and embed faces, but only where the classifier says a face exists.

    python faces_embed.py --thumbs D:\_thumbs --store D:\_enrichment --shard 0/6

WHY THIS IS CHEAP

Running face detection over the whole library means 68,000 images to find the
59% that contain a person. The classification pass has already answered that
question for every file, so this reads its `people` count and only looks where
it was told there is someone. ~47,000 images instead of ~68,000, and the ones
skipped are skipped on evidence rather than on a guess.

The classifier's count is a filter, not a target. It said 2 and the detector
found 1, or said 4 and found none: both happen, and the detector wins, because
it is the thing that actually located a face. The count is only used to decide
whether looking is worthwhile.

WHAT IT WRITES

  faces.csv    one row per detected face: hash, index, bbox, detector score
  faces.f16    the embeddings, 512 float16 each, in row order

Split because 163,000 x 512 floats is 167 MB as float16 and does not belong in
a CSV. float16 rather than float32 because these are compared by cosine
similarity at a threshold around 0.5, and half precision is far below the noise
floor of that decision while halving the file.

RESUMABLE AND SHARDED

Shards split on a hash of the file path, deterministic and disjoint, so six
workers never touch the same image and none of them need to coordinate. A hash
already in faces.csv is skipped, so a killed run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import os
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from batch_classify import assets_for                            # noqa: E402

TAGS = "content_tags.csv"


def load_people(store: str) -> dict:
    """hash -> how many people the classifier reported."""
    out = {}
    p = os.path.join(store, TAGS)
    if not os.path.exists(p):
        return out
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("tag") in ("people", "people_count"):
                try:
                    out[r["hash"]] = max(out.get(r["hash"], 0),
                                         int(str(r["value"]).strip() or 0))
                except ValueError:
                    continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thumbs", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--shard", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--det-size", type=int, default=512)
    a = ap.parse_args()

    shard_i = shard_n = 0
    if a.shard:
        shard_i, shard_n = (int(x) for x in a.shard.split("/"))

    import numpy as np
    from PIL import Image
    from insightface.app import FaceAnalysis

    people = load_people(a.store)
    assets = assets_for(a.thumbs)
    todo = []
    for h, paths in assets.items():
        if people.get(h, 0) < 1:
            continue
        if shard_n and (zlib.crc32(h.encode()) % shard_n) != shard_i:
            continue
        todo.append((h, paths[0]))
    todo.sort()
    if a.limit:
        todo = todo[:a.limit]

    out_csv = os.path.join(a.store, "faces.csv")
    out_emb = os.path.join(a.store, "faces.f16")
    if shard_n:
        out_csv = out_csv.replace(".csv", ".{}.csv".format(shard_i))
        out_emb = out_emb.replace(".f16", ".{}.f16".format(shard_i))

    done = set()
    if os.path.exists(out_csv):
        with open(out_csv, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r:
                    done.add(r[0])
    todo = [t for t in todo if t[0] not in done]

    print("shard {}/{}: {:,} images to look at, {:,} already done".format(
        shard_i, shard_n or 1, len(todo), len(done)))
    if not todo:
        return

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(a.det_size, a.det_size))

    fresh = not os.path.exists(out_csv)
    cf = open(out_csv, "a", newline="", encoding="utf-8")
    cw = csv.writer(cf)
    if fresh:
        cw.writerow(["hash", "face_index", "bbox", "det_score", "said"])
    ef = open(out_emb, "ab")

    t0 = time.time()
    nf = 0
    for i, (h, path) in enumerate(todo, 1):
        try:
            img = np.array(Image.open(path).convert("RGB"))[:, :, ::-1]
            faces = app.get(img)
        except Exception:                                        # noqa: BLE001
            faces = []
        for j, fc in enumerate(faces):
            v = np.asarray(fc.embedding, dtype=np.float32)
            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n                        # normalise once, here, so the
            ef.write(v.astype(np.float16).tobytes())   # clusterer never has to
            cw.writerow([h, j,
                         ",".join("{:.0f}".format(x) for x in fc.bbox),
                         "{:.3f}".format(float(fc.det_score)),
                         people.get(h, 0)])
            nf += 1
        # A row with no faces still has to be recorded, or every resumed run
        # re-examines every image the detector found nothing in.
        if not faces:
            cw.writerow([h, -1, "", "0.000", people.get(h, 0)])
        if i % 200 == 0:
            cf.flush()
            ef.flush()
            el = time.time() - t0
            rate = i / max(el, 1)
            print("  {:,}/{:,}  {:,} faces  {:.1f} img/s  ~{:.0f} min left"
                  .format(i, len(todo), nf, rate,
                          (len(todo) - i) / max(rate, 0.01) / 60), flush=True)
    cf.close()
    ef.close()
    print("shard {} done: {:,} images, {:,} faces, {:.0f} min".format(
        shard_i, len(todo), nf, (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
