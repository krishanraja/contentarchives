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

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
# side_of and is_majority_communal were defined HERE and again in
# name_clusters.py - two copies of the rule that decides whose photographs Krish
# is asked about. One definition now, in contentarchives/sides.py, which also
# reads Archive\Personal and _Review\Communal: 1,230 files were unsided purely
# because this function looked only inside \Media\ (2026-09-18). Imported rather
# than re-implemented, and re-exported so every caller and test that reaches for
# `people_sheet.side_of` keeps working.
from sides import side_of, is_majority_communal                  # noqa: E402,F401
FACES = r"D:\_enrichment\faces.0.csv"
THUMBS = r"D:\_thumbs"
OUT = r"D:\_PhotoAudit\PEOPLE.html"
ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS.csv"
# video faces, from assign_video_faces.py; each row names the FRAME it came from
VIDEO_ASSIGN = r"D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv"
FRAMES = r"D:\_frames"
MERGES = r"D:\_PhotoAudit\CLUSTER-MERGES.csv"
# os.path.join, not a literal with a backslash in it. This line was generated
# as "D:\_enrichment\answers.csv", the backslash-a became a BEL character,
# the file was never found, and the "have we already asked this?" check matched
# nothing while reporting "skipping 0 already answered" - which reads like good
# news. A path that cannot be found must not silently mean "nothing there".
ANSWERS = os.path.join(r"D:\_enrichment", "answers.csv")

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
// are pasted back and recorded through stages/07_people/answers.py.
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


_FRAMES = {}
VIDEO_EXT = (".mp4", ".mov", ".avi", ".mts", ".m4v", ".3gp", ".mpg", ".wmv")


def frame_for(path, fhash="", thumbs=r"D:\_thumbs"):
    r"""A sampled frame for a video, or None. PIL cannot open an .mp4.

    Found 2026-09-18 while testing context(): two of the ten worst declined
    clusters rendered ZERO bytes from crop() AND context(), because their faces
    are in videos and both called Image.open on the .mp4. Those rows were blank,
    not low quality.

    Measured before fixing it, because I had just called it a silent hole across
    the whole round: only 8 of the 472 declined clusters are video-only, and 0
    of those lack sampled frames on disk. So the gap is narrow and every case is
    recoverable - the frames were always there, at <hash>_f0..fN.jpg, and
    nothing looked for them.

    The index is built ONCE and cached: assets_for() walks every subdirectory of
    D:\_thumbs, and calling that per face would walk it thousands of times.
    """
    if not path or not path.lower().endswith(VIDEO_EXT):
        return None
    if not _FRAMES:
        try:
            from batch_classify import assets_for
            _FRAMES.update(assets_for(thumbs))
        except Exception:                                        # noqa: BLE001
            _FRAMES["__failed__"] = []
    # assets_for() keys by HASH, not by filename - I wrote that in the comment
    # above and then looked up by stem anyway, which would have indexed the
    # whole thumbs tree and returned None every single time: all of the cost and
    # none of the benefit. The caller holds the hash, so it passes it in.
    got = _FRAMES.get(fhash or "")
    return got[0] if got else None


def context(path, bbox, fhash="", size=600, quality=80):
    r"""The PHOTOGRAPH, with the face marked. For faces that have no pixels.

    WHY THIS EXISTS

    Krish, 2026-09-18: *"Usually the reason I decline to identify is because
    your thumbnail is really low quality."* Measured immediately after: in the
    485 clusters he declined and never named, the BEST face is a median of **25
    source pixels**, 91% are under 104px, and only 9% have any face reaching
    104px at all. So `crop()` was rendering a 4x upscale of 25 pixels and asking
    who it was. He was not refusing; he was being shown nothing.

    A BIGGER CROP CANNOT FIX THAT - the pixels do not exist. What does is the
    frame around the face: the setting, the clothes, who they are standing next
    to. A person is recognisable in a photograph long before their face is
    legible in isolation.

    530 rows across 485 clusters went into the journal as
    `unidentifiable = declined` - "never show this again" - on the strength of
    that thumbnail. Only 10 rows are his actual judgement ("unsure, blurry",
    typed deliberately). The instrument overrode his intent, and this is the
    repair.

    Deliberately NOT like crop():
      - no `return None` for a small box. crop() drops anything under 12px,
        which silently hides exactly the faces this is for. A tiny face inside a
        readable photograph is the case being fixed.
      - the whole frame, scaled on its LONG edge, so the aspect ratio survives
        and a portrait does not become a square.
      - one per ROW, never one per crop: a 600px context JPEG is tens of times
        the bytes of a 104px face, and 60 rows x 12 would be a 40 MB page.
    """
    from PIL import Image, ImageDraw
    try:
        with Image.open(frame_for(path, fhash) or path) as im:
            im = im.convert("RGB")
            W, H = im.size
            x1, y1, x2, y2 = [float(v) for v in bbox.split(",")]
            d = ImageDraw.Draw(im)
            # Two rings, light on dark, so the box reads on any photograph.
            pen = max(2, int(round(max(W, H) / 320)))
            d.rectangle([x1, y1, x2, y2], outline=(0, 0, 0), width=pen * 2)
            d.rectangle([x1, y1, x2, y2], outline=(255, 210, 60), width=pen)
            scale = min(1.0, float(size) / max(W, H))
            if scale < 1.0:
                im = im.resize((max(1, int(W * scale)), max(1, int(H * scale))),
                               Image.LANCZOS)
            b = io.BytesIO()
            im.save(b, "JPEG", quality=quality)
            return base64.b64encode(b.getvalue()).decode("ascii")
    except Exception:                                            # noqa: BLE001
        return None


def crop(path, bbox, fhash="", size=104):
    """The face itself, not the photograph it is in.

    Right when the face HAS pixels: 34% of named clusters carry a face of 104px
    or more. Useless when it does not - see context() above, and the 25-pixel
    median that made 485 clusters unanswerable.
    """
    from PIL import Image
    try:
        # NOT `h`: three lines down, `w, h = x2 - x1, y2 - y1` rebinds h to the
        # face HEIGHT. Two meanings for one name, two lines apart, is a trap
        # that survives review by working today.
        with Image.open(frame_for(path, fhash) or path) as im:
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


def known_clusters(tags: str) -> set:
    """Every cluster the tag store holds - the set a recorded answer can reach."""
    out = set()
    if not os.path.exists(tags):
        return out
    with io.open(tags, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("tag") == "cluster" and r.get("value"):
                out.add(r["value"])
    return out


SUBJECT_SHARE = 0.08


def is_subject(bbox, frame, share=SUBJECT_SHARE):
    r"""Is this person a SUBJECT of the photograph, or someone in the background?

    Krish, 2026-09-18, shown a page of the smallest faces in his declined
    clusters: *"All those boxes are just people in the background, not really
    important"*. A face 8 pixels wide in a 512-pixel thumbnail is 1.6% of the
    frame - it IS a background person, and he had been right to decline all of
    them. The repair is not a better rendering; it is not asking.

    Measured across the 54,229-group queue: median best face 0.062 of the
    frame's short edge, against 0.146 for every cluster he NAMED. Two different
    populations. 90% of the queue is under 60 thumbnail pixels.

    WHY A SHARE AND NOT PIXELS. He chose "30px" from counts built on absolute
    thumbnail pixels, which leans on thumbnails being <=512px on the long edge.
    Approximately true, and wrong in the way that matters: 30px is 0.059 of one
    frame's short edge and 0.316 of another, so the same face is a subject in a
    portrait and background in a landscape. Re-derived as a share, 0.08 gives
    ~19,776 groups keeping ~72% of what he named - his 17,764 / 71% within
    sampling error, so the choice stands, but it was checked and could have
    failed (at 0.06 it is 28,127 groups, at 0.12 it is 11,207).

    The SHORT edge, because a face is taller than it is wide and the short edge
    is what limits how large a person can appear in the frame.

    `frame` is (width, height) of the image the bbox was measured against - the
    THUMBNAIL, not the library file: 99.2% of bboxes fit thumbnail dimensions
    and only 0.5% fit the full-resolution image.
    """
    try:
        x1, y1, x2, y2 = [float(v) for v in str(bbox).split(",")]
    except (ValueError, AttributeError):
        return False
    short = min(frame) if frame and min(frame) > 0 else 0
    if not short:
        # No dimensions: keep it. Being asked about a background face costs a
        # glance; dropping a subject because a thumbnail would not open loses a
        # person for good.
        return True
    return (min(x2 - x1, y2 - y1) / float(short)) >= share


def is_recordable(cluster: str, known: set) -> bool:
    """Can an answer about this cluster be recorded AND reach photographs?

    record_people.py refuses a cluster that is not in the tag store, and
    build_db's scope_hashes expands a cluster answer with
    `SELECT hash FROM tags WHERE tag='cluster' AND value=?` - so an untagged
    cluster is both unrecordable and, if forced in, inert.

    Round 19, 2026-09-17: five rows Krish answered came back "no such cluster".
    They were singletons, which cluster_faces.py leaves out of the store by
    design. THE SAME function the test calls, so the rule cannot drift between
    the sheet and its test.
    """
    return cluster in known


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # THE SHEET MUST NOT OFFER A ROW THE STORE CANNOT HOLD.
    #
    # Round 19, 2026-09-17: five rows Krish answered came back "no such
    # cluster". cluster_faces.py writes a tag only for a cluster of TWO or more
    # faces - "a cluster of one is not yet a person" - but this sheet ranks from
    # FACE-CLUSTERS.csv, which holds every face including the 40,006 singletons.
    # So the sheet offered rows that record_people.py refuses and build_db's
    # scope_hashes (SELECT ... FROM tags WHERE tag='cluster') would expand onto
    # nothing. His answers had nowhere to land.
    #
    # Asked which way to resolve it, he chose: never offer them again, and leave
    # the >=2 rule alone. So this reads the same tag store the recorder
    # validates against, and the sheet, the recorder and the expansion now share
    # ONE notion of a known cluster.
    ap.add_argument("--tags", default=os.path.join(r"D:\_enrichment",
                                                   "content_tags.csv"),
                    help="the tag store; a cluster with no tag here cannot be "
                         "recorded, so it is never offered")
    ap.add_argument("--faces", default=FACES)
    ap.add_argument("--merges", default=MERGES,
                    help="group clusters that are the same person")
    ap.add_argument("--answers", default=ANSWERS)
    ap.add_argument("--include-named", action="store_true",
                    help="show people already named (default: skip them)")
    ap.add_argument("--assign", default=ASSIGN,
                    help="per-face cluster assignments from cluster_faces.py")
    ap.add_argument("--thumbs", default=THUMBS)
    ap.add_argument("--video-assign", default=VIDEO_ASSIGN)
    ap.add_argument("--frames", default=FRAMES)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--per-row", type=int, default=12)
    # SUBJECT OR BACKGROUND. Krish, 2026-09-18, shown the smallest faces in the
    # clusters he had declined: "All those boxes are just people in the
    # background, not really important." He chose a "30px" floor from a page of
    # counts; re-derived as a share of the frame's SHORT edge that is 0.08,
    # which reproduces the pair he chose from (~19,776 groups, ~72% of what he
    # had named) within sampling error. A share and not pixels because 30px is
    # 0.059 of one frame's short edge and 0.316 of another - the same face is a
    # subject in a portrait and background in a landscape.
    #
    # 0 disables it and shows everything, which is what every sheet up to round
    # 23 did: 90% of that queue was under 60 thumbnail pixels.
    ap.add_argument("--min-face-share", type=float, default=SUBJECT_SHARE,
                    metavar="F",
                    help="skip a face smaller than this share of the frame's "
                         "short edge - background people rather than subjects "
                         "(default %(default)s; 0 shows everything)")
    # THE ROUNDS HAVE TO BE ABLE TO END, AND TO SAY SO.
    #
    # Krish, 2026-09-16, asked how round 19 should pick its 60: "add a size floor
    # and stop". Reach per round had fallen from 1,058 photographs to 540, because
    # the big clusters are all named and the ranking keeps offering whatever is
    # largest among what is left - eventually three-face clusters, for ever.
    #
    # The floor is on PHOTOGRAPHS covered, which is what the ranking below sorts
    # by and what a row is worth answering for. When nothing clears it this says
    # the naming rounds are DONE and writes no sheet, because an empty page and a
    # finished job look identical to whoever opens it (learning 44).
    ap.add_argument("--min-photos", type=int, default=0, metavar="N",
                    help="skip clusters covering fewer than N photographs, and "
                         "say the rounds are DONE when none clears the floor")
    # Krish, 2026-09-17, at the end of round 14's answers: "Do not make me
    # identify any more faces from Communal any more." Communal is Bharti's to
    # enrich (decided 2026-09-15); this sheet ranked purely by photographs
    # covered and knew nothing about side, which is how he came to be asked
    # round after round.
    #
    # He was offered the wider reading - exclude the unsided
    # Pending-Segmentation and NoDate material too, where the scanned old photo
    # libraries live - and chose true Communal only. So this drops a cluster
    # whose photographs are MAJORITY Communal and nothing else. Measured when
    # it was written: 4,054 of 58,033 unnamed clusters, and the next sheet goes
    # from 639 photographs to 636.
    ap.add_argument("--include-communal", action="store_true",
                    help="show clusters that are majority Communal photographs "
                         "(default: skip them - they are Bharti's)")
    # Show exactly these clusters, in this order, whatever else is true of them.
    #
    # Krish, 2026-09-17: "I have labelled two different people Kiran, one of
    # them should be Kiran Nathwani." There are THREE Kiran clusters in the
    # journal - c306 (157 photographs, 2012-2026), c1160 (11) and c1165 (10) -
    # plus c4122, the new Kiran Nathwani, and none of them share a merge group.
    # Nothing in the data says which two he means or which becomes Nathwani, and
    # relabelling the wrong one renames a real person across every photograph
    # they appear in. So he needs to SEE them side by side.
    #
    # The normal selection cannot do that: it ranks by photographs covered and
    # skips anything already answered, and all four of these are answered by
    # definition. This bypasses both, and only those two - the crop logic is
    # untouched, so the faces shown are the same faces verify_people_sheet.py
    # checks against the assignment files.
    ap.add_argument("--clusters", default="",
                    help="comma-separated cluster ids to show, in order, "
                         "ignoring the ranking and the already-answered filter")
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
    # Clusters are grouped by CLUSTER-MERGES.csv, so one person who fragmented
    # into eleven clusters is one row rather than eleven. Krish named eleven
    # separate "Krish" rows last time; that is the thing being fixed.
    group_of = {}
    if os.path.exists(a.merges):
        for r in csv.DictReader(io.open(a.merges, encoding="utf-8", newline="")):
            group_of[r["cluster"]] = r["group"]

    clusters = collections.defaultdict(list)    # group -> [face rows]
    for r in csv.DictReader(io.open(a.assign, encoding="utf-8",
                                    errors="replace", newline="")):
        if r.get("bbox"):
            clusters[group_of.get(r["cluster"], r["cluster"])].append(r)
    if os.path.exists(a.video_assign):
        nv = 0
        for r in csv.DictReader(io.open(a.video_assign, encoding="utf-8",
                                        errors="replace", newline="")):
            if r.get("bbox"):
                clusters[group_of.get(r["cluster"], r["cluster"])].append(r)
                nv += 1
        print("video faces: {:,}".format(nv))
    print("face groups: {:,}".format(len(clusters)))

    # Already answered? Do not ask again. A name recorded by a human covers the
    # whole group, and re-showing it wastes the only scarce thing here.
    named = set()
    if not os.path.exists(a.answers):
        # NOT a silent zero. A missing answers file and an empty one look
        # identical to `if os.path.exists(...)`, and the difference is whether
        # Krish gets asked to name fifty people he has already named.
        print("STOPPING: no answers file at {}".format(a.answers))
        print("If nothing has been named yet, pass --include-named. Otherwise fix")
        print("the path - proceeding would re-ask every question already answered.")
        return 1
    for r in csv.DictReader(io.open(a.answers, encoding="utf-8", newline="")):
        if r.get("field") in ("person", "needs_identifying", "unidentifiable"):
            named.add(group_of.get(r["target"], r["target"]))
    print("already answered: {} groups".format(len(named)))
    if not a.include_named:
        before = len(clusters)
        clusters = {g: v for g, v in clusters.items() if g not in named}
        print("skipping {:,} already answered; {:,} left to name".format(
            before - len(clusters), len(clusters)))

    # when the photographs were taken, so a row can say "2009-2024", and which
    # SIDE each one sits on, so Krish is not asked about Bharti's.
    years = {}
    sides = {}
    try:
        import sqlite3
        db = sqlite3.connect("file:{}?mode=ro".format(
            r"D:\_PhotoAudit\library.db".replace("\\", "/")), uri=True)
        try:
            for h, y in db.execute("SELECT hash, MIN(year) FROM files "
                                   "WHERE hash IS NOT NULL AND year!='' GROUP BY hash"):
                years[h] = y
            # PATH, not files.side. That column holds the top-level tree -
            # 'Media', 'Archive', '_Review', 'ContentProduction' - so a first
            # attempt at this filter joined on it, found no cluster with a
            # Personal photograph, and would have excluded all 58,033
            # (learning 54). Personal and Communal are one level down.
            for h, p in db.execute("SELECT hash, path FROM files "
                                   "WHERE hash IS NOT NULL AND hash!=''"):
                sides[h] = side_of(p)
        finally:
            db.close()
    except Exception:                                            # noqa: BLE001
        pass

    # Krish, 2026-09-17: "Do not make me identify any more faces from Communal
    # any more." A cluster is not Personal or Communal - its PHOTOGRAPHS are -
    # so the test is whether Communal outnumbers Personal within it.
    if not a.include_communal:
        if not sides:
            print("STOPPING: no sides could be read from library.db, so every")
            print("cluster would look non-Communal and Krish would be asked about")
            print("Bharti's side again. Fix the database path rather than")
            print("proceeding - an empty filter is worse than no filter.")
            return 1
        before = len(clusters)
        kept = {}
        dropped_photos = 0
        for g, faces in clusters.items():
            hs = {r["hash"] for r in faces}
            # THE SAME function the test calls. This was three inline lines, so
            # a test could only have used a fixture with a database and three
            # CSVs, or reimplemented the rule and agreed with itself.
            if is_majority_communal(hs, sides):
                dropped_photos += len(hs)
            else:
                kept[g] = faces
        clusters = kept
        print("skipping {:,} majority-Communal groups ({:,} photographs) - "
              "Bharti's side; {:,} left".format(
                  before - len(clusters), dropped_photos, len(clusters)))

    # NEVER OFFER A ROW THE STORE CANNOT HOLD (round 19, 2026-09-17).
    # Five rows Krish answered came back "no such cluster", and the decline pass
    # would then have recorded his answers as refusals. Same refusal shape as the
    # Communal guard above: an empty filter is worse than no filter (learning 44).
    known = known_clusters(a.tags)
    if not known:
        print("STOPPING: no cluster tags found in {}".format(a.tags))
        print("  Every row would then look unrecordable, or - if this check were")
        print("  skipped - every row would look fine while none could be")
        print("  recorded. Fix the path rather than proceeding.")
        return 1
    before = len(clusters)
    clusters = {g: v for g, v in clusters.items() if is_recordable(g, known)}
    if before - len(clusters):
        print("skipping {:,} groups with no tag in the store (unrecordable); "
              "{:,} left".format(before - len(clusters), len(clusters)))

    if a.clusters:
        # EXACTLY these, in this order. Bypasses the ranking and the
        # already-answered filter, both of which would drop them: the clusters
        # worth disambiguating are answered by definition (see --clusters).
        wanted = [c.strip() for c in a.clusters.split(",") if c.strip()]
        by_group = collections.defaultdict(list)
        for path in (a.assign, a.video_assign):
            if not os.path.exists(path):
                continue
            for r in csv.DictReader(io.open(path, encoding="utf-8",
                                            errors="replace", newline="")):
                if r.get("bbox"):
                    by_group[group_of.get(r["cluster"], r["cluster"])].append(r)
        # COLLAPSE MERGE GROUPS FIRST. Asking for c36 and c290 - which share
        # group c290 - built two rows from the same pooled faces, and
        # verify_people_sheet.py rightly refused the page: c36's row was showing
        # c290 faces, because the group is the unit the crops come from. The
        # effect was worse than a duplicate row. It asked Krish the same
        # question twice under two different labels, and double-counted 654
        # photographs into a "1,593 photographs" total for ten rows whose true
        # union is far smaller. One row per GROUP, naming every cluster that
        # contributes to it.
        seen_groups, ranked, missing = {}, [], []
        for c in wanted:
            g = group_of.get(c, c)
            if not by_group.get(g):
                missing.append(c)
                continue
            if g in seen_groups:
                seen_groups[g].append(c)
                continue
            seen_groups[g] = [c]
            ranked.append((g, by_group[g]))
        for g, members in seen_groups.items():
            if len(members) > 1:
                print("  {} are one merge group ({}) - shown as a single row"
                      .format(", ".join(members), g))
        if missing:
            # A cluster id with no faces is a typo or a renumbering, and showing
            # three rows when four were asked for is the kind of quiet shortfall
            # that gets believed (learning 54).
            print("STOPPING: no faces found for {}".format(", ".join(missing)))
            print("  Asked for {} clusters, found {}. Check the ids against")
            print("  FACE-CLUSTERS.csv rather than accepting a short page."
                  .format(len(wanted), len(ranked)))
            return 1
        # The GROUPS shown, not the ids asked for. It printed len(ranked)
        # against `wanted`, so a collapsed request read "showing 9 named
        # clusters explicitly" followed by TEN ids - a count and a list that
        # disagree, which a later reader has to stop and reconcile.
        shown = ["{} (+{})".format(g, ", ".join(m[1:])) if len(m) > 1 else g
                 for g, m in seen_groups.items()]
        print("showing {} row(s) from {} requested cluster(s): {}".format(
            len(ranked), len(wanted), ", ".join(shown)))
    else:
        # ranked by PHOTOGRAPHS covered, not faces found: a cluster of 900 faces
        # from one afternoon deserves less attention than 400 across fifteen years
        ranked = sorted(clusters.items(),
                        key=lambda kv: -len({r["hash"] for r in kv[1]}))
        if a.min_photos > 0:
            above = [kv for kv in ranked
                     if len({r["hash"] for r in kv[1]}) >= a.min_photos]
            print("floor: {} of {} cluster(s) cover {}+ photographs".format(
                len(above), len(ranked), a.min_photos))
            if not above:
                # An empty sheet and a finished job look identical to whoever
                # opens it, so this refuses to write one and says which it is.
                best = max((len({r["hash"] for r in kv[1]}) for kv in ranked),
                           default=0)
                print()
                print("THE NAMING ROUNDS ARE DONE.")
                print("  Nothing left covers {}+ photographs - the largest "
                      "unnamed cluster covers {}.".format(a.min_photos, best))
                print("  No sheet written. Lower --min-photos to keep going, or "
                      "hand the tail to the swipe game.")
                return 0
            ranked = above
        ranked = ranked[:a.top]
    out = [HEAD]
    total = 0
    shown = 0
    for cid, faces in ranked:
        hashes = {r["hash"] for r in faces}
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
            # a video face's box was measured on its frame, not the thumbnail
            if r.get("image"):
                p = os.path.join(a.frames, r["hash"][:2], r["image"] + ".jpg")
            else:
                p = os.path.join(a.thumbs, r["hash"][:2], r["hash"] + ".jpg")
            if not os.path.exists(p):
                continue
            # SUBJECT OR BACKGROUND. Krish, 2026-09-18, shown the smallest faces
            # in his declined clusters: "All those boxes are just people in the
            # background, not really important." 90% of the queue is under 60
            # thumbnail pixels, so without this the game is mostly strangers.
            #
            # The dimensions come from the image crop() is about to open anyway,
            # so this costs one extra read rather than a second pass over 54,229
            # groups.
            if a.min_face_share > 0:
                try:
                    from PIL import Image
                    with Image.open(p) as _im:
                        frame = _im.size
                except Exception:                                # noqa: BLE001
                    frame = None
                if not is_subject(r["bbox"], frame, a.min_face_share):
                    continue
            b64 = crop(p, r["bbox"], r["hash"])
            if b64:
                # data-face names WHICH face this crop is, so verify_people_sheet
                # can check each crop against the assignment files independently
                imgs.append('<img data-face="{}:{}:{}" src="data:image/jpeg;base64,{}">'
                            .format(r["hash"], r.get("image") or "", r["face_index"], b64))
        if not imgs:
            continue
        # COUNTED AFTER THE FILTER, NOT BEFORE. With --min-face-share on, a
        # ranked group can lose every face to the subject test: the first run
        # rendered 37 rows and still announced "naming all 60 rows would label
        # 420 photographs", because both figures were accumulated before the
        # filter ran. A page that misreports itself is the fault this whole
        # session has been correcting.
        shown += 1
        total += len(hashes)
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
               'covering {:,} photographs.</p>'.format(shown, total))
    out.append(TAIL)
    io.open(a.out, "w", encoding="utf-8").write("".join(out))
    print()
    print("wrote {}  ({:.1f} MB)".format(a.out, os.path.getsize(a.out) / 1048576))
    print("naming all {} rows would label {:,} photographs.".format(shown, total))
    if shown < len(ranked):
        print("({} of {} ranked groups had no SUBJECT face and were dropped - "
              "background people, at --min-face-share {})".format(
                  len(ranked) - shown, len(ranked), a.min_face_share))
    return 0


if __name__ == "__main__":
    sys.exit(main())
