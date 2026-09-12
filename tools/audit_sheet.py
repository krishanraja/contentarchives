r"""A contact sheet for auditing the classifier by eye, in minutes.

    python audit_sheet.py                 # sample every kind, plus disagreements
    python audit_sheet.py --per-kind 120  # more per section
    python audit_sheet.py --kind meme     # interrogate one label

Writes D:\_PhotoAudit\AUDIT.html. Open it locally.

WHY BY EYE, WHEN THE STATISTICS LOOK FINE

Distribution checks catch a degenerate model - one that answers "photo" to
everything scores 85% on a library that is 85% photographs and tells you nothing.
They cannot catch a model that is confidently wrong in a consistent direction,
and they cannot check a subject line at all. "Mother holding newborn baby" is
either right or it is not, and the only instrument for that is a person looking.

HOW IT IS ARRANGED, AND WHY THAT MATTERS

Tiles are GROUPED BY THE LABEL THE MODEL GAVE. Scanning a wall of images that
are all supposed to be screenshots, a photograph leaps out; the same images
shuffled would hide it. Auditing by label turns a careful comparison into a
glance.

The disagreement section is first because it is the highest-yield: where this
model contradicts the stored one, one of them is wrong, and which one decides
whether a re-classification is an improvement or a regression.

NOT FOR PUBLICATION. This embeds family photographs by local file path. It is a
local artefact, it is written outside the repository on purpose, and it must
never be committed or published.
"""

from __future__ import annotations

import argparse
import collections
import csv
import html
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "engine"))
sys.path.insert(0, r"D:\_PhotoAudit\scripts")
from batch_classify import assets_for                            # noqa: E402

try:
    import paths as P
    AUDIT = P.AUDIT
except Exception:                                                # noqa: BLE001
    AUDIT = r"D:\_PhotoAudit"

STORE = r"D:\_enrichment"
TAGS = os.path.join(STORE, "content_tags.csv")
OUT = os.path.join(AUDIT, "AUDIT.html")
GEMINI = "google/gemini-3.1-flash-lite"
KINDS = ["photo", "screenshot", "meme", "document", "graphic", "poster"]

CSS = """
body{background:#14141a;color:#e8e8ef;font:13px/1.45 system-ui,sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}
h2{font-size:15px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid #33333f;
   position:sticky;top:0;background:#14141a}
.sub{color:#9a9aab;margin:0 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.t{background:#1e1e27;border-radius:8px;overflow:hidden;border:1px solid #2c2c38}
.t img{width:100%;height:150px;object-fit:cover;display:block;background:#000}
.m{padding:7px 9px}
.k{font-weight:600}
.s{color:#b9b9c8;margin:2px 0}
.f{color:#8a8a9b;font-size:11px}
.warn{border-color:#7a4a20}
.bad{color:#ff9b6a}
.ok{color:#7fd18b}
"""


def load_tags():
    g = collections.defaultdict(dict)
    h = collections.defaultdict(dict)
    with open(TAGS, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            (g if r["source"] == GEMINI else h)[r["hash"]][r["tag"]] = r["value"]
    return g, h


def tile(hsh, thumb, d, note=""):
    kind = html.escape(str(d.get("kind", "?")))
    subj = html.escape(str(d.get("subject", "")))[:70]
    sens = str(d.get("sensitivity", ""))
    keep = str(d.get("keep", ""))
    era = html.escape(str(d.get("era", "")))
    people = str(d.get("people", ""))
    place = html.escape(str(d.get("place", "")))
    cls = "t warn" if note else "t"
    sc = ' class="bad"' if sens in ("intimate", "private-family") else ""
    bits = [x for x in (era, place, "people " + people if people else "",
                        "keep " + keep) if x]
    return (
        '<div class="{}"><img loading="lazy" src="file:///{}">'
        '<div class="m"><div class="k">{}</div>'
        '<div class="s">{}</div>'
        '<div class="f"{}>{}</div>'
        '{}</div></div>').format(
            cls, html.escape(thumb.replace(chr(92), "/")), kind, subj, sc,
            html.escape(" · ".join(bits)),
            '<div class="f bad">{}</div>'.format(html.escape(note))
            if note else "")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-kind", type=int, default=80)
    ap.add_argument("--kind", default="")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    g, hk = load_tags()
    assets = assets_for(r"D:\_thumbs")
    rnd = random.Random(a.seed)
    parts = [CSS.join(["<style>", "</style>"]),
             "<h1>Classifier audit</h1>",
             '<p class="sub">{:,} files judged by {}. '
             'Grouped by the label the model gave, so a wrong one stands out. '
             'Orange = the stored label disagreed. '
             'Nothing here leaves this machine.</p>'.format(len(g), GEMINI)]

    # Highest-yield section first: where the two models disagree.
    dis = [x for x in g if x in hk and hk[x].get("kind")
           and g[x].get("kind") and hk[x]["kind"] != g[x]["kind"]]
    if dis and not a.kind:
        rnd.shuffle(dis)
        parts.append("<h2>Disagreements with the stored label &mdash; {:,} of "
                     "{:,} judged by both</h2>".format(
                         len(dis), sum(1 for x in g if x in hk)))
        parts.append('<p class="sub">The question for each: which label is '
                     'right? If the new one usually is, re-classifying is an '
                     'improvement. If not, stop.</p><div class="grid">')
        for x in dis[:a.per_kind]:
            if x in assets:
                parts.append(tile(x, assets[x][0], g[x],
                                  "stored: " + hk[x]["kind"]))
        parts.append("</div>")

    # Then one section per label.
    by = collections.defaultdict(list)
    for x, d in g.items():
        if d.get("kind"):
            by[d["kind"]].append(x)
    for k in ([a.kind] if a.kind else KINDS):
        xs = by.get(k, [])
        if not xs:
            continue
        rnd.shuffle(xs)
        parts.append('<h2>{} &mdash; {:,} files</h2>'.format(
            html.escape(k), len(xs)))
        parts.append('<p class="sub">Every tile should be a {}. '
                     'Anything that is not, is an error.</p>'
                     '<div class="grid">'.format(html.escape(k)))
        for x in xs[:a.per_kind]:
            if x in assets:
                parts.append(tile(x, assets[x][0], g[x]))
        parts.append("</div>")

    # And the two that carry consequences.
    for tag, val, why in (("sensitivity", "intimate", "quarantined"),
                          ("sensitivity", "private-family",
                           "kept, never shown in the game")):
        xs = [x for x, d in g.items() if d.get(tag) == val]
        if not xs:
            continue
        rnd.shuffle(xs)
        parts.append('<h2>{}: {} &mdash; {:,} files ({})</h2>'.format(
            tag, html.escape(val), len(xs), why))
        parts.append('<p class="sub">A false positive here hides a memory. '
                     'A false negative exposes one.</p><div class="grid">')
        for x in xs[:a.per_kind]:
            if x in assets:
                parts.append(tile(x, assets[x][0], g[x]))
        parts.append("</div>")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print("wrote " + OUT)
    print("open it locally. It references thumbnails by file path and is not "
          "for publication.")


if __name__ == "__main__":
    main()
