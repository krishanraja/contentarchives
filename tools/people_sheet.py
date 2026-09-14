r"""A page of faces to name, one row per person, so fifty answers label thousands.

    python people_sheet.py --top 60

WHY A CONTACT SHEET AND NOT A LIST

Krish has twice caught real classification errors by looking at a grid of
pictures - the screenshots two models agreed on and got wrong, and the 442
receipts - and neither would have been visible in a table of filenames. A face
is the same: nobody recognises their mother from a cluster id and a cosine
score.

So this crops the actual face out of each thumbnail using the bbox the detector
recorded, and puts twelve of them in a row. One row is one cluster. The question
for each row is the only question a machine cannot answer: who is this?

WHAT TO DO WITH IT

Each row shows the exact command to record the answer:

    j.record("cluster", "c14", "person", "Mum")

which is appended to the answers journal - never edited, never overwritten - and
expanded by build_db onto every photograph that cluster appears in. Naming the
top 15 rows labels about 15,000 photographs.

THE ROWS ARE ORDERED BY REACH, NOT BY SIZE

By photographs covered rather than faces detected, because a cluster of 900
faces that are all from one afternoon is worth less of Krish's attention than
one of 400 spread over fifteen years.
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import io
import os
import sys

FACES = r"D:\_enrichment\faces.0.csv"
THUMBS = r"D:\_thumbs"
OUT = r"D:\_PhotoAudit\PEOPLE.html"

HEAD = """<!doctype html><meta charset="utf-8"><title>Who is this?</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:24px;background:#111;color:#eee}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#999;margin-bottom:24px}
 .row{border-top:1px solid #333;padding:14px 0;display:flex;gap:16px;align-items:flex-start}
 .meta{min-width:250px}
 .id{font-size:17px;font-weight:600}
 .n{color:#9ad;font-size:13px}
 code{background:#222;padding:3px 6px;border-radius:4px;font-size:12px;
      color:#8f8;display:inline-block;margin-top:6px;user-select:all}
 .faces img{height:104px;width:104px;object-fit:cover;border-radius:6px;
            margin:0 5px 5px 0;background:#222}
 .yr{color:#777;font-size:12px}
</style>
<h1>Who is this?</h1>
<div class="sub">One row per person. Naming a row labels every photograph in it.
Copy the command, or just tell Claude "c14 is Mum".</div>
"""


def crop(path, bbox, size=104):
    """The face itself, not the photograph it is in."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            W, H = im.size
            x1, y1, x2, y2 = [float(v) for v in bbox.split(",")]
            # a little context around the box reads far better than a tight crop
            w, h = x2 - x1, y2 - y1
            pad = 0.35
            box = (max(0, int(x1 - w * pad)), max(0, int(y1 - h * pad)),
                   min(W, int(x2 + w * pad)), min(H, int(y2 + h * pad)))
            if box[2] - box[0] < 12 or box[3] - box[1] < 12:
                return None
            im = im.crop(box).resize((size, size), Image.LANCZOS)
            b = io.BytesIO()
            im.save(b, "JPEG", quality=72)
            return base64.b64encode(b.getvalue()).decode("ascii")
    except Exception:                                            # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--faces", default=FACES)
    ap.add_argument("--thumbs", default=THUMBS)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--per-row", type=int, default=12)
    a = ap.parse_args()

    # cluster ids live in the tag store, written by cluster_faces.py --apply
    clusters = collections.defaultdict(set)
    tags = r"D:\_enrichment\content_tags.csv"
    for r in csv.DictReader(io.open(tags, encoding="utf-8", errors="replace",
                                    newline="")):
        if r.get("tag") == "cluster":
            clusters[r["value"]].add(r["hash"])
    if not clusters:
        print("no cluster tags in the store - run cluster_faces.py --apply first")
        return 1
    print("clusters in the store: {:,}".format(len(clusters)))

    rows = [r for r in csv.DictReader(
                io.open(a.faces, encoding="utf-8", errors="replace", newline=""))
            if r.get("bbox") and (r.get("face_index") or "-1").lstrip("-").isdigit()
            and int(r["face_index"]) >= 0]
    byhash = collections.defaultdict(list)
    for r in rows:
        byhash[r["hash"]].append(r)

    # when the photographs were taken, so a row can say "2009-2024"
    years = {}
    try:
        import sqlite3
        db = sqlite3.connect(r"D:\_PhotoAudit\library.db")
        for h, y in db.execute("SELECT hash, MIN(year) FROM files "
                               "WHERE hash IS NOT NULL AND year!='' GROUP BY hash"):
            years[h] = y
    except Exception:                                            # noqa: BLE001
        pass

    ranked = sorted(clusters.items(), key=lambda kv: -len(kv[1]))[:a.top]
    out = [HEAD]
    total = 0
    for cid, hashes in ranked:
        total += len(hashes)
        ys = sorted(y for y in (years.get(h) for h in hashes) if y)
        span = "{}-{}".format(ys[0], ys[-1]) if ys else ""
        # the best-detected faces, they are the most recognisable
        cand = []
        for h in hashes:
            for r in byhash.get(h, []):
                cand.append(r)
        cand.sort(key=lambda r: -float(r["det_score"]))
        imgs = []
        for r in cand:
            if len(imgs) >= a.per_row:
                break
            p = os.path.join(a.thumbs, r["hash"][:2], r["hash"] + ".jpg")
            if not os.path.exists(p):
                continue
            b64 = crop(p, r["bbox"])
            if b64:
                imgs.append('<img src="data:image/jpeg;base64,{}">'.format(b64))
        if not imgs:
            continue
        out.append(
            '<div class="row"><div class="meta"><div class="id">{cid}</div>'
            '<div class="n">{n:,} photographs</div>'
            '<div class="yr">{span}</div>'
            '<code>j.record("cluster", "{cid}", "person", "NAME")</code>'
            '</div><div class="faces">{imgs}</div></div>'.format(
                cid=cid, n=len(hashes), span=span, imgs="".join(imgs)))
        print("  {:<8} {:>6,} photographs  {}".format(cid, len(hashes), span))

    out.append('<p class="sub" style="margin-top:24px">{} rows shown, '
               'covering {:,} photographs.</p>'.format(len(ranked), total))
    io.open(a.out, "w", encoding="utf-8").write("".join(out))
    print()
    print("wrote {}  ({:.1f} MB)".format(a.out, os.path.getsize(a.out) / 1048576))
    print("naming all {} rows would label {:,} photographs.".format(len(ranked), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
