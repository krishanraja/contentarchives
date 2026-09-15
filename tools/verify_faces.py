r"""Re-derive a sample of face embeddings and check they match what was stored.

    python verify_faces.py                 # exits 0 if correct, 1 if not
    python verify_faces.py --sample 12

WHY RE-DERIVING, AND NOT CHECKING THE SHAPE

On 2026-09-13 every face embedding written after the first kill belonged to a
different photograph than the row describing it, and every cheap check passed:

    rows well-formed          yes
    vectors unit-norm         yes, all 34,203 of them
    row count plausible       yes, within the write buffer
    process exit code         0
    progress climbing         yes, steadily, for five hours

The output was valid in every respect except being right. The only test that
could tell the difference was recomputing an embedding from its thumbnail and
comparing it to the one on disk - cosine 1.00 where it is correct, about 0.00
where it is not. It takes about ninety seconds.

So this is the correctness check the checkpoint runs while the work is still
going, rather than a post-mortem. It samples from the END of the file, because
that is where a drift that started mid-run shows up first, plus a few from the
start to catch a file that was wrong from the beginning.

Exit code is the whole interface: 0 correct, 1 wrong, 2 could not tell.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import os
import sys

THRESH = 0.95


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=r"D:\_enrichment\faces.0.csv")
    ap.add_argument("--thumbs", default=r"D:\_thumbs")
    ap.add_argument("--frames", default=r"D:\_frames",
                    help="for faces.video.csv, whose rows name their frame")
    ap.add_argument("--sample", type=int, default=8)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    def say(m):
        if not a.quiet:
            print(m, flush=True)

    if not os.path.exists(a.csv):
        say("verify: no {} yet".format(a.csv))
        return 2

    # The producer appends while this reads, and its buffer flushes at arbitrary
    # byte offsets, so the last line can be half a row: half an embedding, which
    # decodes wrong and reads as corruption (learning 42). A verify that fails
    # on that kills a healthy run. Anything after the final newline is still
    # being written; it is left for the next check.
    def complete_lines(f):
        prev = None
        for ln in f:
            if prev is not None:
                yield prev
            prev = ln
        if prev is not None and prev.endswith("\n"):
            yield prev

    rows = []
    with io.open(a.csv, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(complete_lines(f)):
            if r.get("emb") and (r.get("face_index") or "-1").isdigit():
                rows.append(r)
    if len(rows) < 4:
        say("verify: only {} face rows so far, nothing to check".format(len(rows)))
        return 2

    import numpy as np
    from PIL import Image
    import warnings
    warnings.filterwarnings("ignore")
    from insightface.app import FaceAnalysis

    # Mostly from the tail: a drift that begins mid-run is correct at the start
    # and wrong at the end, so checking only the start would have passed.
    n = len(rows)
    k = max(2, a.sample // 4)
    picks = [rows[i] for i in range(min(k, n))]
    picks += [rows[n - 1 - i] for i in range(min(a.sample - k, n - k))]

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(512, 512))

    checked = mismatch = 0
    for r in picks:
        h = r["hash"]
        # a video face is re-derived from the frame it was found in
        if r.get("image"):
            p = os.path.join(a.frames, h[:2], r["image"] + ".jpg")
        else:
            p = os.path.join(a.thumbs, h[:2], h + ".jpg")
        if not os.path.exists(p):
            continue
        try:
            got = app.get(np.array(Image.open(p).convert("RGB"))[:, :, ::-1])
        except Exception:                                        # noqa: BLE001
            continue
        idx = int(r["face_index"])
        if idx < 0 or idx >= len(got):
            continue                      # the detector is allowed to disagree
        v = np.asarray(got[idx].embedding, dtype=np.float32)
        v /= max(float(np.linalg.norm(v)), 1e-9)
        try:
            stored = np.frombuffer(base64.b64decode(r["emb"]),
                                   dtype=np.float16).astype(np.float32)
        except Exception:                                        # noqa: BLE001
            mismatch += 1
            checked += 1
            say("  {}  embedding will not decode".format(h[:12]))
            continue
        if stored.shape[0] != 512:
            mismatch += 1
            checked += 1
            say("  {}  embedding is {}d, not 512".format(h[:12], stored.shape[0]))
            continue
        cos = float(np.dot(v, stored))
        checked += 1
        if cos <= THRESH:
            mismatch += 1
            say("  {}  idx {}  cosine {:.4f}  MISMATCH".format(h[:12], idx, cos))

    if checked == 0:
        # NOT "can't tell". The file has rows and none of them could be
        # re-derived - missing images, a detector that will not load. A check
        # with no failure mode is not a check (learning 6), and the chain treats
        # 2 as acceptable, so this has to be 1.
        say("verify: could not re-derive ANY of {} sampled rows from a file of "
            "{:,} - that is a failure, not a pass".format(len(picks), n))
        return 1
    say("verify: recomputed {} of {:,} face rows, {} mismatched".format(
        checked, n, mismatch))
    return 1 if mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
