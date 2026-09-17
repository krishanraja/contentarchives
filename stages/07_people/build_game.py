r"""One batch of the naming game: a phone page that survives the session closing.

    python build_game.py --who krish  --batch 1 --size 40
    python build_game.py --who bharti --batch 1 --size 40

Writes `D:\_PhotoAudit\GAME-<who>-<batch>.html` and a manifest CSV of exactly
which clusters and crops went into it.

WHY THIS IS A BUILDER AND NOT A HAND-WRITTEN PAGE

Krish, 2026-09-18: *"you need to account for the fact that this session might be
closed when I am on my phone doing the classification game"*. A page I write by
hand cannot be regenerated for batch 2, or for Bharti, and
`verify_people_sheet.py` could not check that every crop belongs to the row it
is shown in. The gates exist because a sheet once showed six different people in
one row.

IT REUSES people_sheet's SELECTION, IT DOES NOT RESTATE IT

Every filter below exists because it failed once:

  - faces from FACE-CLUSTERS.csv, never the tag store: the store says "this
    photograph contains c14" and cannot say WHICH face is c14
  - merge groups collapsed, so a person who fragmented into eleven clusters is
    one question
  - already answered - person, needs_identifying OR unidentifiable - is never
    asked again: a refusal is an answer
  - `is_recordable`: never offer a row the store cannot hold. Five of Krish's
    round 19 answers were refused as "no such cluster" and the decline pass
    would have turned them into refusals
  - `is_subject`: 90% of the queue is people in the BACKGROUND of other
    photographs, which is what his declines had always been about
  - `is_majority_communal`: Krish is not asked about Bharti's side, and hers is
    the inverse

WHAT THE PAGE DOES THAT THE SHEET DOES NOT

  - one cluster per screen, sized for a phone
  - a datalist of every name already in the journal, so "Lauren" is PICKED and
    never retyped as "lauren" or "Laurenn". Preventing that at source is the
    whole defence: the two Kirans and the three Rishis are what happens when it
    is repaired afterwards
  - answers held in localStorage AND written to the artifact `db` on submit, so
    a closed tab loses nothing and a closed session loses nothing
  - each answer row carries the batch id and cluster id the ingester expects
"""

from __future__ import annotations

import argparse
import collections
import csv
import html
import io
import json
import os
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
import people_sheet as PS                                        # noqa: E402
from sides import side_of, is_majority_communal                  # noqa: E402

ANSWERS = os.path.join(r"D:\_enrichment", "answers.csv")
TAGS = os.path.join(r"D:\_enrichment", "content_tags.csv")


def known_names(answers: str) -> list:
    """Every name already given, most-used first - the autocomplete list."""
    n = collections.Counter()
    if not os.path.exists(answers):
        return []
    for r in csv.DictReader(io.open(answers, encoding="utf-8", newline="")):
        if r.get("field") == "person" and r.get("value"):
            v = r["value"].strip()
            if v and not v.lower().startswith(("for ", "unsure")):
                n[v] += 1
    return [name for name, _ in n.most_common()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--who", choices=("krish", "bharti"), default="krish")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--size", type=int, default=40)
    ap.add_argument("--assign", default=PS.ASSIGN)
    ap.add_argument("--video-assign", default=PS.VIDEO_ASSIGN)
    ap.add_argument("--merges", default=PS.MERGES)
    ap.add_argument("--answers", default=ANSWERS)
    ap.add_argument("--tags", default=TAGS)
    ap.add_argument("--thumbs", default=PS.THUMBS)
    ap.add_argument("--frames", default=PS.FRAMES)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--min-face-share", type=float, default=PS.SUBJECT_SHARE)
    ap.add_argument("--out", default="")
    # A published artifact is wrapped in the platform's own <head>, so the page
    # must start at <title> with no doctype or meta. A LOCAL file needs both, or
    # the browser renders it in quirks mode and the layout shifts under me.
    # Same page, two envelopes.
    ap.add_argument("--artifact", action="store_true",
                    help="omit the doctype/meta prologue, for publishing")
    a = ap.parse_args()

    if not os.path.exists(a.assign):
        print("STOPPING: no {}".format(a.assign))
        print("  The tag store cannot say WHICH face is who, and guessing is")
        print("  what produced rows full of strangers.")
        return 1

    group_of = {}
    for r in csv.DictReader(io.open(a.merges, encoding="utf-8", newline="")):
        group_of[r["cluster"]] = r["group"]

    clusters = collections.defaultdict(list)
    for path in (a.assign, a.video_assign):
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(io.open(path, encoding="utf-8",
                                        errors="replace", newline="")):
            if r.get("bbox"):
                clusters[group_of.get(r["cluster"], r["cluster"])].append(r)
    print("face groups: {:,}".format(len(clusters)))

    if not os.path.exists(a.answers):
        print("STOPPING: no answers file at {}".format(a.answers))
        print("  Proceeding would re-ask every question already answered.")
        return 1
    answered = set()
    for r in csv.DictReader(io.open(a.answers, encoding="utf-8", newline="")):
        if r.get("field") in ("person", "needs_identifying", "unidentifiable"):
            answered.add(group_of.get(r["target"], r["target"]))
    clusters = {g: v for g, v in clusters.items() if g not in answered}
    print("unanswered: {:,}".format(len(clusters)))

    known = PS.known_clusters(a.tags)
    if not known:
        print("STOPPING: no cluster tags in {}".format(a.tags))
        print("  Every row would be unrecordable, or - worse - look fine and")
        print("  record nothing. An empty filter is worse than no filter.")
        return 1
    clusters = {g: v for g, v in clusters.items() if PS.is_recordable(g, known)}
    print("recordable: {:,}".format(len(clusters)))

    import sqlite3
    sides, years = {}, {}
    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")),
                         uri=True)
    try:
        for h, p in db.execute("SELECT hash, path FROM files "
                               "WHERE hash IS NOT NULL AND hash != ''"):
            sides[h] = side_of(p)
        for h, y in db.execute("SELECT hash, MIN(year) FROM files "
                               "WHERE hash IS NOT NULL AND year != '' "
                               "GROUP BY hash"):
            years[h] = y
    finally:
        db.close()
    if not sides:
        print("STOPPING: no sides could be read from {}".format(a.db))
        return 1

    # Krish gets everything that is NOT majority Communal; Bharti gets the
    # inverse. Neither is shown the other's side.
    want_communal = (a.who == "bharti")
    picked = {}
    for g, faces in clusters.items():
        hs = {r["hash"] for r in faces}
        if is_majority_communal(hs, sides) == want_communal:
            picked[g] = faces
    print("{}'s side: {:,} groups".format(a.who, len(picked)))

    # Largest first, so the earliest batches buy the most.
    ranked = sorted(picked.items(),
                    key=lambda kv: -len({r["hash"] for r in kv[1]}))
    start = (a.batch - 1) * a.size
    rows, manifest = [], []
    for g, faces in ranked[start:]:
        if len(rows) >= a.size:
            break
        hs = {r["hash"] for r in faces}
        ys = sorted(y for y in (years.get(h) for h in hs) if y)
        span = "{}-{}".format(ys[0], ys[-1]) if ys else ""
        seen, imgs = set(), []
        for r in sorted(faces, key=lambda x: -float(x["det_score"])):
            if len(imgs) >= 9 or r["hash"] in seen:
                continue
            h = r["hash"]
            p = (os.path.join(a.frames, h[:2], r["image"] + ".jpg")
                 if r.get("image")
                 else os.path.join(a.thumbs, h[:2], h + ".jpg"))
            if not os.path.exists(p):
                continue
            if a.min_face_share > 0:
                try:
                    from PIL import Image
                    with Image.open(p) as im:
                        frame = im.size
                except Exception:                                # noqa: BLE001
                    frame = None
                if not PS.is_subject(r["bbox"], frame, a.min_face_share):
                    continue
            b64 = PS.crop(p, r["bbox"], h)
            if not b64:
                continue
            seen.add(h)
            imgs.append((h, r.get("image") or "", r["face_index"], b64))
        if not imgs:
            continue
        rows.append({"cid": g, "photos": len(hs), "span": span, "imgs": imgs})
        for h, image, fi, _ in imgs:
            manifest.append({"batch": a.batch, "who": a.who, "cluster": g,
                             "hash": h, "image": image, "face_index": fi})

    if not rows:
        print()
        print("NOTHING LEFT for {} at batch {}.".format(a.who, a.batch))
        print("  Either the batch is past the end of the queue, or every")
        print("  remaining group is background faces. Not writing an empty")
        print("  page: an empty page and a finished job look identical.")
        return 0

    out = a.out or os.path.join(P.AUDIT, "GAME-{}-{}.html".format(
        a.who, a.batch))
    names = known_names(a.answers)
    io.open(out, "w", encoding="utf-8").write(
        page(rows, names, a.who, a.batch, a.artifact))
    man = out.replace(".html", "-manifest.csv")
    with io.open(man, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["batch", "who", "cluster", "hash",
                                           "image", "face_index"])
        w.writeheader()
        w.writerows(manifest)
    print()
    print("wrote {}  ({:.1f} MB)".format(out, os.path.getsize(out) / 1048576))
    print("      {} - {} crops across {} clusters".format(
        man, len(manifest), len(rows)))
    print("{} people in the autocomplete list".format(len(names)))
    print()
    print("Gate it before anyone sees it:")
    print("    python stages/07_people/verify_people_sheet.py --page {}".format(out))
    return 0


def page(rows, names, who, batch, artifact=False):
    """The phone page. One cluster per screen, answers kept locally AND sent.

    `artifact` omits the doctype/meta prologue, because a published artifact is
    wrapped in the platform's own <head> and a stray doctype inside the body is
    invalid. A local file keeps it, or the browser drops into quirks mode.
    """
    # A JS array, not <option> elements: the datalist this replaced was rendered
    # by Android as a full-screen list of all 290 names, covering the Skip
    # button. json.dumps escapes quotes and non-ASCII for a <script> context.
    names_js = json.dumps(names, ensure_ascii=True)
    cards = []
    for i, r in enumerate(rows):
        imgs = "".join(
            '<img data-face="{}:{}:{}" src="data:image/jpeg;base64,{}">'.format(
                html.escape(h), html.escape(im), html.escape(str(fi)), b64)
            for h, im, fi, b64 in r["imgs"])
        # `<div class="row" data-cid=... data-photos=...>`, in that exact
        # shape, because verify_people_sheet.py's ROW regex needs the two
        # attributes ADJACENT and terminates each row on a lookahead for
        # `<div class="row"` or `<p class="sub">`. My first version emitted
        # `<section class="card">` with a data-i between them, so the gate
        # parsed ZERO rows and refused the page - correctly.
        #
        # The page bends to the gate, never the other way round. That verifier
        # exists because a sheet once showed six different people in one row,
        # and loosening a safety check to accommodate a new generator is how a
        # gate quietly stops checking anything.
        cards.append(
            '<div class="row" data-cid="{cid}" data-photos="{n}" '
            'data-i="{i}"><div class="faces">{imgs}</div>'
            '<div class="meta"><b>{n:,}</b> photograph{s}{span}</div>'
            '<input type="text" id="n{i}" placeholder="who is this?" '
            'autocomplete="off" autocapitalize="words" spellcheck="false">'
            '<div class="chips"></div>'
            '<div class="btns"><button type="button" class="skip">Skip</button>'
            '<button type="button" class="next">Next</button></div></div>'.format(
                cid=html.escape(r["cid"]), n=r["photos"],
                s="" if r["photos"] == 1 else "s",
                span=(" &middot; " + html.escape(r["span"])) if r["span"] else "",
                i=i, imgs=imgs))
    body = TEMPLATE.replace("{{NAMES}}", names_js) \
                   .replace("{{CARDS}}", "".join(cards)) \
                   .replace("{{WHO}}", html.escape(who)) \
                   .replace("{{BATCH}}", str(batch)) \
                   .replace("{{COUNT}}", str(len(rows)))
    return body if artifact else PROLOGUE + body


PROLOGUE = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
"""

# The palette is the subject's own: a darkroom under a safelight. Amber is what
# you can leave on while paper is exposed, which is also why it is the only warm
# thing in the room. Committed to a single dark theme on purpose - a face is
# judged against a dark ground, not a bright one - so every colour is painted
# explicitly rather than inherited from a host theme.
TEMPLATE = """<title>Who Is This?</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
 :root{
   --ground:#16130f; --surface:#211c16; --edge:#332b22;
   --ink:#f2ece2; --muted:#a2937d; --safelight:#e8a33d; --named:#8fbf6a;
   color-scheme:dark;
 }
 *{box-sizing:border-box}
 html,body{height:100%}
 body{margin:0;background:var(--ground);color:var(--ink);
      font:400 16px/1.55 "IBM Plex Sans",system-ui,sans-serif;
      padding:0 16px 104px}
 header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
        padding-block:18px 10px}
 h1{font:600 26px/1.1 "Newsreader",Georgia,serif;margin:0;
    letter-spacing:-.01em;text-wrap:balance}
 .who{font:500 11px/1 "IBM Plex Mono",ui-monospace,monospace;
      text-transform:uppercase;letter-spacing:.14em;color:var(--safelight)}
 .sub{color:var(--muted);font-size:14px;margin:0 0 16px;max-width:60ch}
 /* the rail encodes position in the batch - it is information, not decoration */
 #rail{height:2px;background:var(--edge);margin-bottom:18px}
 #railfill{height:2px;background:var(--safelight);width:0;transition:width .2s}
 .row{display:none}
 .row.on{display:block}
 .faces{display:flex;gap:6px;overflow-x:auto;padding-bottom:6px;
        margin-bottom:14px;scrollbar-width:thin}
 .faces img{width:108px;height:108px;flex:0 0 auto;object-fit:cover;
            border-radius:3px;background:var(--surface);
            border:1px solid var(--edge)}
 .meta{font:400 12px/1.4 "IBM Plex Mono",ui-monospace,monospace;
       color:var(--muted);letter-spacing:.02em;margin-bottom:12px;
       font-variant-numeric:tabular-nums}
 .meta b{color:var(--ink);font-weight:500}
 input[type=text]{width:100%;padding:14px 15px;
   font:400 18px/1.2 "IBM Plex Sans",system-ui,sans-serif;
   border-radius:4px;border:1px solid var(--edge);
   background:var(--surface);color:var(--ink)}
 input[type=text]::placeholder{color:var(--muted)}
 input[type=text]:focus{outline:2px solid var(--safelight);outline-offset:1px;
   border-color:var(--safelight)}
 /* A phone cannot use a 290-entry <datalist>: Android renders it as a
    full-screen list that covered the Skip button entirely. These are the same
    names as tappable chips - most-used first, filtered as you type - in a strip
    that never covers anything. */
 .chips{display:flex;gap:6px;overflow-x:auto;padding:10px 0 2px;
        scrollbar-width:thin}
 .chip{flex:0 0 auto;padding:9px 13px;border-radius:999px;
   border:1px solid var(--edge);background:var(--surface);color:var(--ink);
   font:400 15px/1 "IBM Plex Sans",system-ui,sans-serif;cursor:pointer;
   white-space:nowrap}
 .chip:focus-visible{outline:2px solid var(--safelight)}
 .chip.pick{border-color:var(--safelight);color:var(--safelight)}
 .btns{display:flex;gap:8px;margin-top:12px}
 .btns button{flex:1;padding:14px;font:500 15px/1 "IBM Plex Sans",sans-serif;
   border-radius:4px;border:1px solid var(--edge);background:transparent;
   color:var(--muted);cursor:pointer}
 .btns button:focus-visible{outline:2px solid var(--safelight)}
 .btns .next{background:var(--safelight);color:#241a08;border-color:var(--safelight);
   font-weight:600}
 #end{color:var(--muted);font-size:14px;padding-block:18px}
 #bar{position:fixed;left:0;right:0;bottom:0;background:var(--surface);
   border-top:1px solid var(--edge);padding:12px 16px;
   padding-bottom:calc(12px + env(safe-area-inset-bottom,0px));
   display:flex;gap:12px;align-items:center}
 #tally{font:500 13px/1 "IBM Plex Mono",ui-monospace,monospace;
        color:var(--muted);font-variant-numeric:tabular-nums}
 #tally b{color:var(--named);font-weight:500}
 #msg{font-size:13px;color:var(--named)}
 #send{margin-left:auto;padding:12px 20px;
   font:600 15px/1 "IBM Plex Sans",sans-serif;border-radius:4px;border:0;
   background:var(--safelight);color:#241a08;cursor:pointer}
 #send[disabled]{opacity:.45;cursor:default}
 @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<header>
  <h1>Who is this?</h1>
  <span class="who">{{WHO}} &middot; batch {{BATCH}}</span>
</header>
<p class="sub">{{COUNT}} people, most photographed first. Pick a name from the
list when it offers one &mdash; that is what keeps one person from becoming
three. Skip anyone you cannot place; they will not come back.</p>
<div id="rail"><div id="railfill"></div></div>
{{CARDS}}
<p class="sub" id="end">That is the batch. Hit Submit and it is safe to close.</p>
<div id="bar">
  <span id="tally"><b id="done">0</b> / {{COUNT}} named</span>
  <span id="msg"></span>
  <button id="send">Submit</button>
</div>
<script>
// Two places, on purpose. localStorage means a closed tab is not a lost hour;
// the artifact db means a closed SESSION is not a lost hour either - which is
// the thing Krish asked for. Neither is the record: the journal is, written by
// stages/07_people/ingest_game_answers.py when these rows are read back.
const KEY = 'contentarchives.game.{{WHO}}.{{BATCH}}';
const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
// Every name already in the journal, most-used first. Picking one is what keeps
// one person from becoming three, so they are offered as chips rather than
// buried in a control the phone renders full-screen.
const NAMES = {{NAMES}};

function suggest(card) {
  const inp = card.querySelector('input');
  const box = card.querySelector('.chips');
  if (!inp || !box) return;
  const q = (inp.value || '').trim().toLowerCase();
  const hits = (q ? NAMES.filter(n => n.toLowerCase().includes(q)) : NAMES)
                 .slice(0, 12);
  box.textContent = '';
  hits.forEach(n => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip' + (n.toLowerCase() === q ? ' pick' : '');
    b.textContent = n;               // textContent, so a name is never markup
    b.addEventListener('click', () => {
      inp.value = n;
      save();
      suggest(card);
    });
    box.appendChild(b);
  });
}
// `.row`, not `.card`: the element is named for verify_people_sheet.py's ROW
// regex, which needs `<div class="row" data-cid=... data-photos=...>`. Renaming
// the markup and leaving this selector behind would render an empty page with
// every gate passing.
const cards = Array.from(document.querySelectorAll('.row'));
let at = 0;

function show(i) {
  cards.forEach((c, n) => c.classList.toggle('on', n === i));
  at = Math.max(0, Math.min(i, cards.length - 1));
  // NO AUTOFOCUS. Krish, on a phone: "Trying to skip completely ruins the
  // experience and tries to force me to pick someone and doesn't let me
  // continue." Focusing the input on arrival opened the keyboard AND - while
  // this used a <datalist> - a full-screen list of all 290 names that covered
  // the Skip button. He could not get past a face without naming it. The field
  // is tapped when he wants it, not thrust at him.
  if (cards[at]) suggest(cards[at]);
  // The rail encodes HOW FAR THROUGH the batch you are. Without this it is a
  // line that never moves - a structural device decorating rather than saying
  // anything, which is worse than no rail at all.
  const fill = document.getElementById('railfill');
  if (fill) fill.style.width = ((at + 1) / cards.length * 100) + '%';
  window.scrollTo(0, 0);
}

function save() {
  const o = {};
  cards.forEach(c => {
    const v = (c.querySelector('input').value || '').trim();
    if (v) o[c.dataset.cid] = v;
  });
  localStorage.setItem(KEY, JSON.stringify(o));
  document.getElementById('done').textContent = Object.keys(o).length;
}

function rows() {
  return cards.map(c => {
    const v = (c.querySelector('input').value || '').trim();
    return v ? {id: '{{WHO}}-{{BATCH}}-' + c.dataset.cid,
                cluster: c.dataset.cid, name: v} : null;
  }).filter(Boolean);
}

cards.forEach((c, i) => {
  const inp = c.querySelector('input');
  if (saved[c.dataset.cid]) inp.value = saved[c.dataset.cid];
  inp.addEventListener('input', () => { save(); suggest(c); });
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); save(); show(i + 1); }
  });
  c.querySelector('.next').addEventListener('click', () => { save(); show(i + 1); });
  c.querySelector('.skip').addEventListener('click', () => {
    inp.value = ''; save(); show(i + 1);
  });
});
show(0);
save();

document.getElementById('send').addEventListener('click', async () => {
  const msg = document.getElementById('msg');
  const data = rows();
  if (!data.length) { msg.textContent = 'nothing named yet'; return; }
  const btn = document.getElementById('send');
  btn.disabled = true;
  msg.textContent = 'sending...';
  try {
    const db = await window.claude.use('db');
    if (!db) throw new Error('no db');
    // One document per batch, replaced wholesale: re-submitting after adding a
    // few more names must not create a second, partial record of the same work.
    await db.doc('answers/{{WHO}}-{{BATCH}}').set(
      {who: '{{WHO}}', batch: {{BATCH}}, rows: data,
       at: new Date().toISOString()});
    msg.textContent = 'sent - ' + data.length + ' names. Safe to close.';
  } catch (e) {
    msg.textContent = 'could not send; your answers are still saved here.';
    btn.disabled = false;
  }
});
</script>
"""


if __name__ == "__main__":
    sys.exit(main())
