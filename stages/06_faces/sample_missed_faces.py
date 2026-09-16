r"""How many faces are we throwing away by trusting the classifier's people count?

    python sample_missed_faces.py --sample 300

WHY THIS QUESTION IS WORTH 10 MINUTES

faces_embed only opens images the classifier said contain at least one person.
That is what makes it affordable - 47,000 images instead of 82,000 - and it is
also a single point of failure: any face the classifier missed is invisible to
the enrichment game for ever, and nothing downstream can tell the difference
between "nobody in this photograph" and "nobody looked".

Measured 2026-09-13: 23,835 real photographs carry people=0 and will never be
examined. Their subjects read plausibly - "sydney skyline and harbour", "rocky
coastal cliff" - but a person small in the frame gets described exactly that way.

So rather than argue about it, or spend eleven hours closing a hole that may not
exist, open a random sample of them and count. Entirely local: insightface on
thumbnails, no API, no network, no cost.

READ THE OUTPUT LIKE THIS

  ~0% with faces      the classifier is right, the shortcut is sound, stop.
  a few %             a real but small loss, probably not worth 11 hours.
  10%+                ~2,400 people-bearing photographs are missing from the
                      game; run the full pass before the naming session, because
                      naming is where their absence becomes permanent.

It also reports detector confidence, because a face found at 0.51 in a landscape
is usually a rock, and one found at 0.85 is usually a person.
"""

from __future__ import annotations

import argparse
import os
import random
import sqlite3
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
DB = r"D:\_PhotoAudit\library.db"
THUMBS = r"D:\_thumbs"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--thumbs", default=THUMBS)
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--det-size", type=int, default=512)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    db = sqlite3.connect(a.db)
    rows = db.execute(
        """SELECT hash, subject FROM v_files
           WHERE people='0' AND kind='photo' AND hash IS NOT NULL AND hash!=''
           GROUP BY hash""").fetchall()
    print("photographs the classifier says contain nobody: {:,}".format(len(rows)))
    if not rows:
        return 2
    random.seed(a.seed)
    random.shuffle(rows)

    import numpy as np
    from PIL import Image
    import warnings
    warnings.filterwarnings("ignore")
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(a.det_size, a.det_size))

    looked = with_faces = total_faces = 0
    confident = 0            # det_score >= 0.75, i.e. probably really a person
    examples = []
    for h, subject in rows:
        if looked >= a.sample:
            break
        p = os.path.join(a.thumbs, h[:2], h + ".jpg")
        if not os.path.exists(p):
            continue
        try:
            faces = app.get(np.array(Image.open(p).convert("RGB"))[:, :, ::-1])
        except Exception:                                        # noqa: BLE001
            continue
        looked += 1
        if faces:
            with_faces += 1
            total_faces += len(faces)
            best = max(float(f.det_score) for f in faces)
            if best >= 0.75:
                confident += 1
                if len(examples) < 10:
                    examples.append((best, len(faces), subject or ""))
        if looked % 50 == 0:
            print("  ...{} examined, {} with a face".format(looked, with_faces),
                  flush=True)

    if not looked:
        print("could not open any thumbnails")
        return 2

    pct = 100.0 * with_faces / looked
    cpct = 100.0 * confident / looked
    print()
    print("examined            : {:,}".format(looked))
    print("with ANY face       : {:,}  ({:.1f}%)".format(with_faces, pct))
    print("with a CONFIDENT    : {:,}  ({:.1f}%)   det_score >= 0.75".format(
        confident, cpct))
    print("faces found         : {:,}".format(total_faces))
    print()
    missed = int(len(rows) * cpct / 100.0)
    print("extrapolated across all {:,}: about {:,} photographs with a".format(
        len(rows), missed))
    print("confidently-detected person that the game will never show you.")
    if examples:
        print()
        print("examples the classifier called peopleless:")
        for score, n, subj in examples:
            print('   det {:.2f}  {} face(s)  "{}"'.format(score, n, subj[:52]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
