r"""Detect and embed faces, but only where the classifier says a face exists.

    python faces_embed.py --thumbs D:\_thumbs --store D:\_enrichment --shard 0/6
    python faces_embed.py --frames D:\_frames --store D:\_enrichment
    python faces_embed.py --frames D:\_frames --store D:\_enrichment --dry-run

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

VIDEO FRAMES (--frames)

The filter above was built from ONE thumbnail per video, taken 10% in. A video
whose thumbnail showed nobody can be full of people three minutes later, so
--frames reads every frame video_face_frames.py sampled, with no filter at all.
It writes faces.video.csv, which carries the frame each face came from, because
a bounding box is meaningless without the image it was measured on - drawing a
frame's box on the video's thumbnail crops a stranger or a wall.

WHAT IT WRITES

  faces.csv        one row per detected face: hash, index, bbox, detector score,
                   and the 512-d embedding itself, base64 of float16, in the row
  faces.video.csv  the same, plus `image`: the frame the face was found in

  face_index -1    the image was read and has no face
  face_index -2    the image could NOT be read. Recorded, so a resumed run does
                   not retry a broken file for ever, and counted separately, so
                   an unreadable image is never mistaken for an empty one
                   (learning 41). --dry-run reports how many.

--dry-run prints what is outstanding NOW and exits before loading the model. The
chain's postcondition uses it; without it, asking "is anything left?" would START
the remaining work inside the check, unsupervised (learning 47).

ONE FILE, BECAUSE TWO FILES DRIFTED APART AND CORRUPTED 11,000 IMAGES

The embeddings used to live in a parallel faces.f16, matched to the CSV BY
POSITION - the Nth row described the Nth vector. Two files, two buffers, and a
machine that kills long jobs routinely. A kill between the CSV flush and the
binary flush leaves the binary longer than the CSV, and on resume both append,
so every embedding after that point belongs to a different photograph than the
row claiming it.

That happened. Measured on 2026-09-13 by recomputing embeddings and comparing
them to their stored slots: aligned at slots 5, 50, 500, 627, 690, 722 - and
broken from slot 754 onwards, cosine ~0.00 instead of ~1.00, all the way to the
end. Of 11,611 images processed, 264 were trustworthy. Nothing errored, nothing
warned, and the clusters built from it would have confidently grouped strangers
together.

The vector now lives in the row that describes it. One file, one buffer, one
append per face: a kill can lose the last row, which is re-done on resume, and
it cannot shift anything. A CSV of ~131,000 rows at ~1.4 KB is about 180 MB -
which is the price of the failure being impossible rather than merely unlikely.

float16 rather than float32 because these are compared by cosine similarity at
a threshold around 0.5, and half precision is far below the noise floor of that
decision while halving the size.

RESUMABLE AND SHARDED

Shards split on a hash of the file path, deterministic and disjoint, so six
workers never touch the same image and none of them need to coordinate. A hash
already in faces.csv is skipped, so a killed run resumes where it stopped. In
--frames mode the resume key is the FRAME, since one video has many.

One shard is fastest on this machine (measured 2026-09-13: 107 face rows/min on
one, 70 on two or three), because onnxruntime already uses every core.
"""

from __future__ import annotations

import argparse
import base64
import csv
import os
import re
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from batch_classify import assets_for                            # noqa: E402

TAGS = "content_tags.csv"
FRAME = re.compile(r"^([0-9a-f]{64})_t(\d+)\.jpg$")


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


def frame_images(root: str) -> list[tuple[str, str, str]]:
    """-> [(hash, frame stem, path)] for every sampled video frame under root.

    Matches finished frames only: video_face_frames.py writes <x>.tmp.jpg and
    renames, so a half-written frame never looks like one. A root that does not
    exist raises rather than yielding nothing (learning 34)."""
    if not os.path.isdir(root):
        raise SystemExit("STOPPING: no frames directory at {}".format(root))
    out = []
    for sub in sorted(os.listdir(root)):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            m = FRAME.match(fn)
            if m:
                out.append((m.group(1), fn[:-4], os.path.join(d, fn)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thumbs", default="",
                    help="photograph thumbnails, filtered by the classifier")
    ap.add_argument("--frames", default="",
                    help="video frames from video_face_frames.py, unfiltered")
    ap.add_argument("--store", required=True)
    ap.add_argument("--shard", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--det-size", type=int, default=512)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what is outstanding now, load no model, write nothing")
    a = ap.parse_args()
    if bool(a.thumbs) == bool(a.frames):
        ap.error("pass exactly one of --thumbs or --frames")

    shard_i = shard_n = 0
    if a.shard:
        shard_i, shard_n = (int(x) for x in a.shard.split("/"))

    # todo rows are (resume key, hash, image path)
    todo = []
    if a.frames:
        people = {}
        for h, stem, path in frame_images(a.frames):
            if shard_n and (zlib.crc32(h.encode()) % shard_n) != shard_i:
                continue
            todo.append((stem, h, path))
        out_csv = os.path.join(a.store, "faces.video.csv")
        header = ["hash", "image", "face_index", "bbox", "det_score", "emb"]
        key_col, idx_col = 1, 2
    else:
        people = load_people(a.store)
        for h, paths in assets_for(a.thumbs).items():
            if people.get(h, 0) < 1:
                continue
            if shard_n and (zlib.crc32(h.encode()) % shard_n) != shard_i:
                continue
            todo.append((h, h, paths[0]))
        out_csv = os.path.join(a.store, "faces.csv")
        header = ["hash", "face_index", "bbox", "det_score", "said", "emb"]
        key_col, idx_col = 0, 1
    todo.sort()
    if shard_n:
        out_csv = out_csv.replace(".csv", ".{}.csv".format(shard_i))

    done, unreadable = set(), set()
    if os.path.exists(out_csv):
        with open(out_csv, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r and r[0] == "hash":
                    continue                 # the header is not a finished image
                if len(r) > idx_col:
                    done.add(r[key_col])
                    if r[idx_col] == "-2":
                        unreadable.add(r[key_col])
    todo = [t for t in todo if t[0] not in done]
    if a.limit:
        todo = todo[:a.limit]

    print("shard {}/{}: {:,} images to look at, {:,} already done, "
          "{:,} unreadable".format(shard_i, shard_n or 1, len(todo), len(done),
                                   len(unreadable)), flush=True)
    if a.dry_run or not todo:
        return 0

    import numpy as np
    from PIL import Image
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(a.det_size, a.det_size))

    fresh = not os.path.exists(out_csv)
    cf = open(out_csv, "a", newline="", encoding="utf-8")
    cw = csv.writer(cf)
    if fresh:
        cw.writerow(header)

    t0 = time.time()
    nf = nbad = 0
    for i, (key, h, path) in enumerate(todo, 1):
        try:
            img = np.array(Image.open(path).convert("RGB"))[:, :, ::-1]
            faces = app.get(img)
        except Exception as e:                                   # noqa: BLE001
            # recorded as UNREADABLE, never as "no faces" (learning 41)
            nbad += 1
            if nbad <= 20:
                print("  unreadable {}: {}".format(os.path.basename(path), e), flush=True)
            if a.frames:
                cw.writerow([h, key, -2, "", "0.000", ""])
            else:
                cw.writerow([h, -2, "", "0.000", people.get(h, 0), ""])
            continue
        for j, fc in enumerate(faces):
            v = np.asarray(fc.embedding, dtype=np.float32)
            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n                    # normalise once, here, so the
            bbox = ",".join("{:.0f}".format(x) for x in fc.bbox)  # clusterer
            det = "{:.3f}".format(float(fc.det_score))            # never has to
            emb = base64.b64encode(v.astype(np.float16).tobytes()).decode("ascii")
            if a.frames:
                cw.writerow([h, key, j, bbox, det, emb])
            else:
                cw.writerow([h, j, bbox, det, people.get(h, 0), emb])
            nf += 1
        # A row with no faces still has to be recorded, or every resumed run
        # re-examines every image the detector found nothing in.
        if not faces:
            if a.frames:
                cw.writerow([h, key, -1, "", "0.000", ""])
            else:
                cw.writerow([h, -1, "", "0.000", people.get(h, 0), ""])
        if i % 200 == 0:
            cf.flush()
            el = time.time() - t0
            rate = i / max(el, 1)
            print("  {:,}/{:,}  {:,} faces  {:,} unreadable  {:.1f} img/s  "
                  "~{:.0f} min left".format(i, len(todo), nf, nbad, rate,
                                            (len(todo) - i) / max(rate, 0.01) / 60),
                  flush=True)
    cf.close()
    print("shard {} done: {:,} images, {:,} faces, {:,} unreadable, {:.0f} min".format(
        shard_i, len(todo), nf, nbad, (time.time() - t0) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
