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
ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"

HEAD = """<!doctype html><meta charset="utf-8"><title>Who is this?</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:24px 24px 140px;background:#111;color:#eee}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#999;margin-bottom:20px}
 .row{border-top:1px solid #333;padding:14px 0;display:flex;gap:16px;align-items:flex-start}
 .row.done{background:#14210f}
 .row.skip{opacity:.4}
 .meta{min-width:260px}
 .id{font-size:17px;font-weight:600}
 .n{color:#9ad;font-size:13px}
 .yr{color:#777;font-size:12px;margin-bottom:8px}
 input[type=text]{width:190px;padding:7px 9px;font-size:15px;border-radius:6px;
   border:1px solid #444;background:#1c1c1c;color:#fff}
 input[type=text]:focus{outline:2px solid #4a8;border-color:#4a8}
 .skipbtn{margin-left:6px;padding:7px 9px;font-size:12px;border-radius:6px;
   border:1px solid #444;background:#1c1c1c;color:#aaa;cursor:pointer}
 .faces img{height:104px;width:104px;object-fit:cover;border-radius:6px;
            margin:0 5px 5px 0;background:#222}
 #bar{position:fixed;left:0;right:0;bottom:0;background:#000;border-top:1px solid #333;
   padding:12px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 #bar b{color:#8f8}
 button.primary{padding:10px 16px;font-size:15px;border-radius:8px;border:0;
   background:#2d7;color:#052;font-weight:600;cursor:pointer}
 button.ghost{padding:10px 14px;font-size:13px;border-radius:8px;
   border:1px solid #444;background:#1c1c1c;color:#ccc;cursor:pointer}
 #out{width:100%;height:96px;margin-top:10px;background:#1c1c1c;color:#8f8;
   border:1px solid #444;border-radius:6px;padding:8px;font-family:ui-monospace,monospace;
   font-size:12px;display:none}
</style>
<h1>Who is this?</h1>
<div class="sub">Type a name, press <b>Enter</b> to jump to the next one. Blank rows are ignored.
Names are kept in this browser, so you can close it and come back.
When you are done, hit <b>Copy all answers</b> and paste them to Claude.</div>
"""

TAIL = """
<div id="bar">
  <div><b id="tally">0</b> named &middot; <b id="reach">0</b> photographs covered</div>
  <button class="primary" onclick="copyAll()">Copy all answers</button>
  <button class="ghost" onclick="clearAll()">Clear</button>
  <span id="msg" style="color:#8f8"></span>
  <textarea id="out" readonly></textarea>
</div>
<script>
// Kept in localStorage so a closed tab is not a lost hour. It is only a
// convenience copy - the real record is the answers journal, written when these
// are pasted back and recorded through engine/answers.py.
const KEY = 'contentarchives.people.v1';
const saved = JSON.parse(localStorage.getItem(KEY) || '{}');

function rows() { return Array.from(document.querySelectorAll('.row')); }

function refresh() {
  let n = 0, reach = 0;
  rows().forEach(r => {
    const inp = r.querySelector('input');
    const v = (inp.value || '').trim();
    r.classList.toggle('done', !!v && v !== '-');
    r.classList.toggle('skip', v === '-');
    if (v && v !== '-') { n++; reach += parseInt(r.dataset.photos, 10) || 0; }
  });
  document.getElementById('tally').textContent = n;
  document.getElementById('reach').textContent = reach.toLocaleString();
}

function save() {
  const o = {};
  rows().forEach(r => {
    const v = (r.querySelector('input').value || '').trim();
    if (v) o[r.dataset.cid] = v;
  });
  localStorage.setItem(KEY, JSON.stringify(o));
  refresh();
}

function answers() {
  return rows().map(r => {
    const v = (r.querySelector('input').value || '').trim();
    return (v && v !== '-') ? r.dataset.cid + ' = ' + v : null;
  }).filter(Boolean).join('\\n');
}

function copyAll() {
  const txt = answers();
  const msg = document.getElementById('msg');
  if (!txt) { msg.textContent = 'nothing named yet'; return; }
  const out = document.getElementById('out');
  // Shown as well as copied: this is a file:// page, where the clipboard API is
  // often blocked, and a button that silently does nothing is worse than a
  // textarea you can select.
  out.style.display = 'block';
  out.value = txt;
  out.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) {}
  if (navigator.clipboard) { navigator.clipboard.writeText(txt).catch(() => {}); }
  msg.textContent = ok ? 'copied - paste it to Claude' : 'select the text below and copy';
}

function clearAll() {
  if (!confirm('Clear every name you have typed?')) return;
  rows().forEach(r => r.querySelector('input').value = '');
  localStorage.removeItem(KEY);
  document.getElementById('out').style.display = 'none';
  refresh();
}

document.addEventListener('DOMContentLoaded', () => {
  const inputs = rows().map(r => r.querySelector('input'));
  rows().forEach((r, i) => {
    const inp = inputs[i];
    if (saved[r.dataset.cid]) inp.value = saved[r.dataset.cid];
    inp.addEventListener('input', save);
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); (inputs[i+1] || inp).focus(); }
    });
    r.querySelector('.skipbtn').addEventListener('click', () => {
      inp.value = inp.value === '-' ? '' : '-';
      save();
    });
  });
  refresh();
});
</script>
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
    ap.add_argument("--assign", default=ASSIGN,
                    help="per-face cluster assignments from cluster_faces.py")
    ap.add_argument("--thumbs", default=THUMBS)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--per-row", type=int, default=12)
    a = ap.parse_args()

    # PER-FACE assignments. Not the tag store.
    #
    # The tag store says "this photograph contains c14" and cannot say which of
    # the faces in it is c14. Reading it and then drawing every face in every
    # matching photograph is what put six or seven different people in a single
    # row - the clusters were right, the picture of them was not. FACE-CLUSTERS
    # .csv is the only place the face-to-person mapping exists, so this reads
    # that and refuses to run without it rather than guessing again.
    if not os.path.exists(a.assign):
        print("no {} - run cluster_faces.py --apply first.".format(a.assign))
        print("Do NOT fall back to the tag store: it cannot say which face is who,")
        print("and guessing is what produced rows full of strangers.")
        return 1
    clusters = collections.defaultdict(list)    # cluster -> [face rows]
    for r in csv.DictReader(io.open(a.assign, encoding="utf-8",
                                    errors="replace", newline="")):
        if r.get("bbox"):
            clusters[r["cluster"]].append(r)
    print("clusters with faces: {:,}".format(len(clusters)))

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

    # ranked by PHOTOGRAPHS covered, not faces found: a cluster of 900 faces from
    # one afternoon deserves less attention than 400 across fifteen years
    ranked = sorted(clusters.items(),
                    key=lambda kv: -len({r["hash"] for r in kv[1]}))[:a.top]
    out = [HEAD]
    total = 0
    for cid, faces in ranked:
        hashes = {r["hash"] for r in faces}
        total += len(hashes)
        ys = sorted(y for y in (years.get(h) for h in hashes) if y)
        span = "{}-{}".format(ys[0], ys[-1]) if ys else ""
        # ONLY the faces assigned to this cluster, best-detected first, and one
        # per photograph so a row is twelve different moments rather than twelve
        # crops of the same instant.
        cand = sorted(faces, key=lambda r: -float(r["det_score"]))
        seen_img = set()
        picked = []
        for r in cand:
            if r["hash"] in seen_img:
                continue
            seen_img.add(r["hash"])
            picked.append(r)
        cand = picked
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
            '<div class="row" data-cid="{cid}" data-photos="{n}">'
            '<div class="meta"><div class="id">{cid}</div>'
            '<div class="n">{n:,} photographs</div>'
            '<div class="yr">{span}</div>'
            '<input type="text" placeholder="who is this?" autocomplete="off" '
            'spellcheck="false">'
            '<button class="skipbtn" title="not a person / skip">&ndash;</button>'
            '</div><div class="faces">{imgs}</div></div>'.format(
                cid=cid, n=len(hashes), span=span, imgs="".join(imgs)))
        print("  {:<8} {:>6,} photographs  {}".format(cid, len(hashes), span))

    out.append('<p class="sub" style="margin-top:24px">{} rows shown, '
               'covering {:,} photographs.</p>'.format(len(ranked), total))
    out.append(TAIL)
    io.open(a.out, "w", encoding="utf-8").write("".join(out))
    print()
    print("wrote {}  ({:.1f} MB)".format(a.out, os.path.getsize(a.out) / 1048576))
    print("naming all {} rows would label {:,} photographs.".format(len(ranked), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
