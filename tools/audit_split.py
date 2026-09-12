r"""Stress-test the Personal / Communal split, at the level it was decided.

    python audit_split.py                 # every origin folder, with evidence
    python audit_split.py --side Personal
    python audit_split.py --min 20        # only folders of 20+ files

Writes D:\_PhotoAudit\AUDIT-SPLIT.html. Open it locally.

WHY BY FOLDER

The split is by ORIGIN FOLDER, by decision: "74,000 file judgements become a few
hundred folder judgements". So the errors it can make are folder-shaped. Auditing
file by file would be 55,691 judgements looking for a mistake that, if it exists,
is the same mistake repeated across a whole folder - and it would hide that
shape rather than show it.

Each row here is one folder, with a strip of its images, its assigned side, its
date range, and the subjects the classifier gave it. The question per row is a
single one: *whose life is this?* A folder is right or wrong all at once.

WHAT TO LOOK FOR, IN ORDER

1. A folder in PERSONAL that is somebody else's. This is the failure that
   matters, because Communal is the smaller and more deliberate set - 3,791
   files against 51,900 - and the default when nothing said otherwise was
   Personal. A family member's device that nobody spotted is sitting in
   Personal right now if this went wrong.
2. A folder in COMMUNAL that is only yours. Less harmful, easily reversed.
3. A folder in PENDING-SEGMENTATION, which is not an error at all - it is the
   queue. Judging these here is the work of the segmentation phase brought
   forward.

WHAT THE SHEET ALREADY CHECKED

No origin folder feeds both sides. If one did, the folder-level rule was not
actually applied to it, and that is reported at the top rather than left to be
noticed.

NOT FOR PUBLICATION. Embeds family photographs by local path, and folder names
that are people's names. Local artefact, written outside the repository.
"""

from __future__ import annotations

import argparse
import collections
import csv
import html
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "engine"))
sys.path.insert(0, r"D:\_PhotoAudit\scripts")
from batch_classify import assets_for                            # noqa: E402

AUDIT = r"D:\_PhotoAudit"
MASTER = os.path.join(AUDIT, "MASTER.csv")
OUT = os.path.join(AUDIT, "AUDIT-SPLIT.html")
SIDES = ["Personal", "Communal", "Pending-Segmentation", "NoDate"]

# Folder names that hint the material is somebody else's. Not a verdict - a
# reason to look first. Deliberately about RELATIONSHIPS and DEVICES rather
# than any particular name, so this file carries no one's name in it.
HINT = re.compile(
    r"(mum|mom|dad|mother|father|parent|nan|gran|grandma|grandad|grandpa|"
    r"aunt|uncle|cousin|sister|brother|sibling|famil|wedding|kids|"
    r"phone|device|backup)", re.I)

CSS = """
body{background:#14141a;color:#e8e8ef;font:13px/1.45 system-ui,sans-serif;margin:0;padding:22px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:30px 0 8px;padding-bottom:5px;
 border-bottom:1px solid #33333f;position:sticky;top:0;background:#14141a;z-index:2}
.sub{color:#9a9aab;margin:0 0 16px;max-width:70em}
.f{background:#1e1e27;border:1px solid #2c2c38;border-radius:9px;margin:0 0 12px;overflow:hidden}
.f.hint{border-color:#7a5a20}
.hd{padding:9px 12px;display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
.nm{font-weight:600;word-break:break-all}
.ct{color:#8a8a9b;font-size:11px}
.pill{font-size:11px;padding:1px 8px;border-radius:20px;background:#2b2b38}
.Personal{background:#24405c} .Communal{background:#5c3a24}
.strip{display:flex;gap:4px;padding:0 8px 9px;overflow-x:auto}
.strip img{height:96px;width:96px;object-fit:cover;border-radius:4px;background:#000;flex:0 0 auto}
.sj{color:#b9b9c8;padding:0 12px 9px;font-size:11px}
.warn{color:#ffb27a}
"""


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--side", default="")
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--strip", type=int, default=10)
    a = ap.parse_args()

    rows = list(csv.DictReader(
        open(MASTER, newline="", encoding="utf-8", errors="replace")))
    assets = assets_for(r"D:\_thumbs")

    folders = collections.defaultdict(lambda: {
        "sides": collections.Counter(), "hashes": [], "years": [],
        "subjects": collections.Counter(), "people": 0, "n": 0})
    for r in rows:
        if r["Side"] not in SIDES:
            continue
        key = r.get("OriginFolder") or "(origin unknown)"
        d = folders[key]
        d["sides"][r["Side"]] += 1
        d["n"] += 1
        if r.get("Hash") in assets and len(d["hashes"]) < a.strip:
            d["hashes"].append(r["Hash"])
        if r.get("Year"):
            d["years"].append(r["Year"])
        if r.get("subject"):
            for w in re.findall(r"[a-z]{4,}", r["subject"].lower()):
                d["subjects"][w] += 1
        try:
            d["people"] += int(r.get("people") or 0)
        except ValueError:
            pass

    # A folder holding both Personal AND Communal means the folder-level
    # rule was not applied to it. A folder spanning a side and the QUEUE
    # (Pending-Segmentation, NoDate) is just work not yet done, and
    # counting those as errors cried wolf on 41 folders when the real
    # number was zero - 41 sources whose dated files are assigned and
    # whose undated ones are still waiting.
    straddle = [k for k, v in folders.items()
                if v["sides"]["Personal"] and v["sides"]["Communal"]]

    parts = ["<style>" + CSS + "</style>",
             "<h1>Personal / Communal split &mdash; folder by folder</h1>",
             '<p class="sub">The split is by origin folder, so an error is a '
             'whole folder on the wrong side. One question per row: '
             '<b>whose life is this?</b> Orange border = the folder name hints '
             'at another person or a device, which is a reason to look, not a '
             'verdict. Nothing here leaves this machine.</p>']

    if straddle:
        parts.append('<p class="sub warn">{} folders hold BOTH Personal and '
                     'Communal files, so the folder-level rule was not applied '
                     'to them. Start here: {}</p>'.format(
                         len(straddle), html.escape(", ".join(straddle[:6]))))
    else:
        parts.append('<p class="sub">No folder holds both Personal and '
                     'Communal files, so the folder-level rule was applied '
                     'consistently. That makes the split uniform, not correct '
                     '&mdash; a folder can be uniformly on the wrong side, which '
                     'is what the rows below are for.</p>')

    order = [a.side] if a.side else SIDES
    for side in order:
        fs = [(k, v) for k, v in folders.items()
              if v["sides"].most_common(1)[0][0] == side and v["n"] >= a.min]
        fs.sort(key=lambda kv: -kv[1]["n"])
        total = sum(v["n"] for _, v in fs)
        parts.append("<h2>{} &mdash; {:,} folders, {:,} files</h2>".format(
            html.escape(side), len(fs), total))
        if side == "Personal":
            parts.append('<p class="sub">Scan for anything that is not yours. '
                         'Personal was the default when no rule said otherwise, '
                         'so this is where a missed family device would be.</p>')
        elif side == "Pending-Segmentation":
            parts.append('<p class="sub">Not errors &mdash; the queue. Deciding '
                         'these is the segmentation phase.</p>')
        for k, v in fs:
            yrs = sorted(set(v["years"]))
            span = ("{}&ndash;{}".format(yrs[0], yrs[-1]) if len(yrs) > 1
                    else (yrs[0] if yrs else "no dates"))
            hint = " hint" if HINT.search(k) else ""
            subj = ", ".join(w for w, _ in v["subjects"].most_common(8))
            parts.append('<div class="f{}"><div class="hd">'
                         '<span class="nm">{}</span>'
                         '<span class="pill {}">{}</span>'
                         '<span class="ct">{:,} files &middot; {} &middot; '
                         '{:,} faces reported</span></div>'.format(
                             hint, html.escape(k), side, side, v["n"], span,
                             v["people"]))
            if v["hashes"]:
                parts.append('<div class="strip">')
                for h in v["hashes"]:
                    parts.append('<img loading="lazy" src="file:///{}">'.format(
                        html.escape(assets[h][0].replace(chr(92), "/"))))
                parts.append("</div>")
            if subj:
                parts.append('<div class="sj">{}</div>'.format(
                    html.escape(subj)))
            parts.append("</div>")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print("wrote " + OUT)
    print("folders: {:,}   straddling both sides: {}".format(
        len(folders), len(straddle)))


if __name__ == "__main__":
    main()
