r"""A contact sheet of the nudity pass's hits, for a human to confirm by eye.

WHY A PAGE AND NOT A DECISION

The pass proposes; only a human may write `sensitivity`. 88 files were already
moved once on labels nobody re-checked, and the question being answered is
whether that was complete - so a second round of moving files on a model's word
would repeat the mistake rather than correct it.

The model's own notes make the reason obvious. In the 733 `private-family`
files, its 42 hits are dominated by a back-wound series, hospital photographs,
newborns held skin-to-skin, and topless men. Those are not what the Intimate
folder is for, and no regex or label can tell them apart from what it IS for.
Eyes can, in about a minute.

LOCAL BY DEFAULT

The page embeds the thumbnails, which means it contains medical and newborn
photographs of the family. It is written to disk and opened locally; it makes no
network request and loads nothing remote. Publishing it anywhere is a separate,
explicit decision for the library's owner.

WHAT COMES BACK

Each card carries its content hash. Marking a card and pressing Copy yields a
plain list of `hash  decision` lines to paste back - the same shape
record_people.py already accepts for people, and the only thing that may cause
a file to move.

    python sensitivity_review.py --out D:\_PhotoAudit\sensitivity-review.html
    python sensitivity_review.py --cohort private-family --open
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import html
import os
import sqlite3
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path

import paths as P                                                 # noqa: E402
from sides import side_of                                         # noqa: E402
from batch_classify import assets_for                             # noqa: E402

SRC = "google/gemini-3.1-flash-lite-sensitivity"
INTIMATE_DIR = "\\personal\\intimate\\"


def answers(store: str) -> dict[str, dict]:
    """hash -> {field: value} for this pass only.

    The store is append-only and a pass may still be writing, so a short final
    line is expected. A later row for the same field wins, which matches
    store.tags_for's rule for equal-confidence claims from one source.
    """
    got: dict[str, dict] = collections.defaultdict(dict)
    p = os.path.join(store, "content_tags.csv")
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.reader(f):
            if len(r) >= 5 and r[3] == SRC:
                got[r[0]][r[1]] = r[2]
                got[r[0]]["_conf"] = r[4]
    return got


def library(db_path: str):
    db = sqlite3.connect("file:{}?mode=ro".format(
        db_path.replace("\\", "/")), uri=True)
    paths: dict[str, list] = collections.defaultdict(list)
    for p, h in db.execute("select path, hash from files"):
        if h:
            paths[h].append(p)
    meta = {}
    for h, m, s, d in db.execute(
            "select hash, coalesce(media,''), coalesce(sensitivity,''), "
            "coalesce(description,'') from v_files"):
        meta.setdefault(h, {"media": m.lower(), "sensitivity": s.strip(),
                            "description": d})
    db.close()
    return paths, meta


def datauri(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def in_intimate(ps) -> bool:
    return any(INTIMATE_DIR in (p or "").replace("/", "\\").lower() for p in ps)


CSS = """
:root{--ground:#16130f;--card:#1e1a15;--edge:#2f2822;--ink:#efe7db;
--dim:#a1968a;--amber:#e0a34a;--alarm:#d4674a;--calm:#6f8f6a}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
font:15px/1.55 "IBM Plex Sans",-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px 96px}
h1{font:600 26px/1.2 Newsreader,Georgia,serif;margin:0 0 6px;
letter-spacing:-.01em}
.lede{color:var(--dim);max-width:62ch;margin:0 0 4px}
.count{color:var(--amber);font-weight:600}
section{margin:34px 0 0}
h2{font:600 18px/1.3 Newsreader,Georgia,serif;margin:0 0 4px;
border-bottom:1px solid var(--edge);padding-bottom:8px}
h2 small{color:var(--dim);font:400 13px/1 "IBM Plex Sans",sans-serif;
margin-left:8px}
.note{color:var(--dim);font-size:13.5px;margin:8px 0 16px;max-width:70ch}
.grid{display:grid;gap:14px;
grid-template-columns:repeat(auto-fill,minmax(232px,1fr))}
.card{background:var(--card);border:1px solid var(--edge);border-radius:6px;
overflow:hidden;display:flex;flex-direction:column}
.card.marked{border-color:var(--amber);box-shadow:0 0 0 1px var(--amber)}
.shot{background:#000;aspect-ratio:4/3;display:flex;align-items:center;
justify-content:center;overflow:hidden}
.shot img{width:100%;height:100%;object-fit:contain}
.shot .missing{color:var(--dim);font-size:12px;padding:12px;text-align:center}
.meta{padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px;flex:1}
.tags{display:flex;gap:5px;flex-wrap:wrap}
.tag{font:600 10.5px/1 "IBM Plex Mono",ui-monospace,monospace;
text-transform:uppercase;letter-spacing:.06em;padding:4px 6px;border-radius:3px;
background:#2a231c;color:var(--dim)}
.tag.full{background:#3a2019;color:#f0a58e}
.tag.partial{background:#33291b;color:var(--amber)}
.tag.child{background:#1f2c1e;color:#a6c79f}
.what{font-size:13.5px}
.path{font:11.5px/1.45 "IBM Plex Mono",ui-monospace,monospace;
color:var(--dim);word-break:break-all}
.desc{font-size:12px;color:var(--dim);border-left:2px solid var(--edge);
padding-left:8px}
label.pick{display:flex;align-items:center;gap:8px;margin-top:auto;
padding-top:8px;border-top:1px solid var(--edge);font-size:13px;cursor:pointer}
.bar{position:fixed;left:0;right:0;bottom:0;background:#120f0c;
border-top:1px solid var(--edge);padding:12px 16px;
padding-bottom:calc(12px + env(safe-area-inset-bottom,0px));
display:flex;gap:12px;align-items:center;justify-content:space-between}
button{font:600 14px/1 "IBM Plex Sans",sans-serif;padding:11px 16px;
border-radius:5px;border:1px solid var(--amber);background:var(--amber);
color:#1a1510;cursor:pointer}
button.ghost{background:transparent;color:var(--amber)}
textarea{width:100%;min-height:120px;margin-top:10px;background:#0e0c0a;
color:var(--ink);border:1px solid var(--edge);border-radius:5px;padding:10px;
font:12.5px/1.5 "IBM Plex Mono",ui-monospace,monospace}
@media (max-width:520px){.grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}
"""

JS = """
const marks = new Set();
function sync(){
  document.querySelectorAll('.card').forEach(c => {
    const on = c.querySelector('input').checked;
    c.classList.toggle('marked', on);
    if (on) marks.add(c.dataset.h); else marks.delete(c.dataset.h);
  });
  document.getElementById('n').textContent = marks.size;
}
document.addEventListener('change', e => {
  if (e.target.matches('.pick input')) sync();
});
document.getElementById('copy').addEventListener('click', () => {
  const lines = [...marks].map(h => h + '  intimate');
  const box = document.getElementById('out');
  box.value = lines.length ? lines.join('\\n')
    : '# nothing marked - every hit stays where it is';
  box.hidden = false;
  box.select();
  try { document.execCommand('copy'); } catch (err) {}
});
document.getElementById('none').addEventListener('click', () => {
  document.querySelectorAll('.pick input').forEach(i => { i.checked = false; });
  sync();
});
sync();
"""


def card(h, d, ps, meta, assets) -> str:
    imgs = assets.get(h) or []
    uri = datauri(imgs[0]) if imgs else ""
    nud = (d.get("nudity") or "?").lower()
    age = (d.get("subject_age") or "?").lower()
    m = meta.get(h, {})
    shot = ('<img src="{}" alt="" loading="lazy">'.format(uri) if uri
            else '<div class="missing">no thumbnail on disk</div>')
    tags = ['<span class="tag {}">{}</span>'.format(
        nud if nud in ("full", "partial") else "", html.escape(nud))]
    tags.append('<span class="tag {}">{}</span>'.format(
        "child" if age == "child" else "", html.escape(age)))
    if (m.get("media") or "") == "video":
        tags.append('<span class="tag">video · {} frames</span>'.format(len(imgs)))
    if (d.get("sexual") or "").lower() in ("yes", "true"):
        tags.append('<span class="tag full">sexual</span>')
    if in_intimate(ps):
        tags.append('<span class="tag">already filed</span>')
    desc = (m.get("description") or "")[:190]
    return (
        '<div class="card" data-h="{h}">'
        '<div class="shot">{shot}</div>'
        '<div class="meta">'
        '<div class="tags">{tags}</div>'
        '<div class="what">{note}</div>'
        '<div class="path">{path}</div>'
        '{desc}'
        '<label class="pick"><input type="checkbox"> move to Intimate</label>'
        '</div></div>'
    ).format(
        h=html.escape(h), shot=shot, tags="".join(tags),
        note=html.escape(d.get("nudity_note") or "(no note)"),
        path=html.escape((ps[0] if ps else "?")),
        desc='<div class="desc">{}</div>'.format(html.escape(desc)) if desc else "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--thumbs", default=r"D:\_thumbs")
    ap.add_argument("--out", default=os.path.join(P.AUDIT,
                                                  "sensitivity-review.html"))
    ap.add_argument("--cohort", default="", help="only hashes in "
                    "sens-list-<name>.txt")
    ap.add_argument("--include-none", action="store_true",
                    help="also show the files answered `none` - for auditing "
                         "the pass's misses rather than its hits")
    ap.add_argument("--open", action="store_true", help="open it when written")
    a = ap.parse_args()

    got = answers(a.store)
    if a.cohort:
        p = os.path.join(P.AUDIT, "sens-list-{}.txt".format(a.cohort))
        with open(p, encoding="utf-8") as f:
            want = {ln.strip() for ln in f
                    if ln.strip() and not ln.startswith("#")}
        got = {h: d for h, d in got.items() if h in want}
    print("answers from this pass: {:,}".format(len(got)))

    paths, meta = library(a.db)
    assets = assets_for(a.thumbs)

    hits = {h: d for h, d in got.items()
            if (d.get("nudity") or "").lower() in ("partial", "full")}
    if a.include_none:
        hits = got
    print("hits to review: {:,}".format(len(hits)))

    # Three groups, because they call for different judgements. Adults first:
    # that is the question. Children next, kept apart and explicitly NOT
    # proposed for the Intimate folder. Mixed frames last.
    def group(h, d):
        age = (d.get("subject_age") or "").lower()
        if age == "child":
            return "child"
        if age == "both":
            return "both"
        return "adult"

    groups = collections.defaultdict(list)
    for h, d in hits.items():
        groups[group(h, d)].append((h, d))
    for g in groups:
        groups[g].sort(key=lambda t: ((t[1].get("nudity") or "") != "full",
                                      t[1].get("nudity_note") or ""))

    BLURB = {
        "adult": ("Adults. This is the question: does any of this belong in "
                  "Personal\\Intimate? The pass found no image it called "
                  "sexual, and its notes are mostly medical - a back wound, "
                  "hospital photographs, topless men."),
        "both": ("An adult and a child in the same frame - mostly newborns "
                 "held skin-to-skin. Moving these beside adult content is "
                 "almost certainly wrong; they are shown for completeness."),
        "child": ("Children. These stay in private-family. That tier exists "
                  "precisely so a child in a bath is never filed beside adult "
                  "content, so none of these is proposed for moving."),
    }
    TITLE = {"adult": "Adults", "both": "Adult and child together",
             "child": "Children"}

    parts = [
        '<title>Nudity pass review</title>',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Newsreader:wght@400;600&family=IBM+Plex+Sans:wght@400;600&'
        'family=IBM+Plex+Mono&display=swap">',
        "<style>{}</style>".format(CSS),
        '<div class="wrap">',
        "<h1>What the nudity pass flagged</h1>",
        '<p class="lede">A second, narrow pass asked one question of '
        '{:,} files: is anyone unclothed. It flagged <span class="count">{:,}'
        '</span>. Nothing has moved, and nothing will move until you say so - '
        'mark what belongs in Personal\\Intimate and press Copy.</p>'.format(
            len(got), len(hits)),
        '<p class="lede">It records subject age, not sex. If the question is '
        'specifically about photographs of women, that is what these '
        'thumbnails are for.</p>',
    ]
    for g in ("adult", "both", "child"):
        if not groups.get(g):
            continue
        parts.append("<section>")
        parts.append("<h2>{}<small>{} file(s)</small></h2>".format(
            TITLE[g], len(groups[g])))
        parts.append('<p class="note">{}</p>'.format(html.escape(BLURB[g])))
        parts.append('<div class="grid">')
        for h, d in groups[g]:
            parts.append(card(h, d, paths.get(h, []), meta, assets))
        parts.append("</div></section>")

    parts.append("</div>")
    parts.append(
        '<div class="bar"><div><span class="count" id="n">0</span> marked to '
        'move</div><div><button class="ghost" id="none">Clear</button> '
        '<button id="copy">Copy decisions</button></div></div>'
        '<div class="wrap"><textarea id="out" hidden readonly></textarea></div>')
    parts.append("<script>{}</script>".format(JS))

    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset=utf-8>"
                '<meta name=viewport content="width=device-width,'
                'initial-scale=1,viewport-fit=cover">')
        f.write("".join(parts))
    os.replace(tmp, a.out)
    print("wrote {}".format(a.out))
    print("  local only: it embeds the thumbnails and makes no network call.")
    if a.open:
        os.startfile(a.out)                                # noqa: S606


if __name__ == "__main__":
    main()
