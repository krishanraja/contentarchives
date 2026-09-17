r"""Look at the proposed split. Groups of photographs, not rows of file paths.

    python review_split_by_path.py
    python review_split_by_path.py --max-groups 200

Writes `D:\_PhotoAudit\SPLIT-BY-PATH.html`. Open it locally.

WHY THIS EXISTS

`propose_split_by_path.py` writes 18,985 rows of source and destination, and I
opened that CSV and asked Krish to review it. His answer: *"what am i supposed to
do in that sheet? Its just cells with text in it"* - which is right. Nobody can
check 18,985 file paths, and a review nobody can perform is not a safeguard, it
is a rubber stamp with extra steps.

So the same trick that made the split tractable in the first place: judge GROUPS.
Filenames carry the device batch that produced them -

    bharti phone upto sept 2019 481.mp4
    bharti phone upto sept 2019 3103.mp4

- so collapsing digit runs turns those into one group of 582 files with one
question attached: whose phone was that? A few hundred groups, each with its
photographs on screen.

WHAT TO LOOK FOR, IN ORDER

1. In **PERSONAL**, anything that is plainly somebody else's device or archive.
   This is the failure that matters: Personal is what a file gets by falling
   through, so a family member's phone that no signal caught is sitting in
   Krish's own chronology.
2. In **COMMUNAL**, anything that is actually his. Smaller and easier to
   reverse, but it hides his own photographs on Bharti's side.
3. **NoDate** groups have no date at all - they are grouped by name only, and
   6,513 of the 6,514 fall through to Personal on no evidence either way. He was
   told that number before choosing.

NOT FOR PUBLICATION. Embeds family photographs by local path, and filenames that
are people's names. Local artefact, written outside the repository.
"""

from __future__ import annotations

import argparse
import collections
import csv
import html
import io
import os
import re
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from batch_classify import assets_for                            # noqa: E402

IN = os.path.join(P.AUDIT, "SPLIT-BY-PATH.csv")
OUT = os.path.join(P.AUDIT, "SPLIT-BY-PATH.html")
THUMBS = r"D:\_thumbs"
YEAR = re.compile(r"\\((?:19|20)\d\d)\\")
DIGITS = re.compile(r"\d+")

HEAD = """<!doctype html><meta charset="utf-8">
<title>Proposed split - review by group</title>
<style>
 body{background:#14151a;color:#e8e8ea;font:14px/1.5 system-ui,sans-serif;
      margin:0;padding:24px 20px 80px}
 h1{font-size:20px;margin:0 0 4px} h2{font-size:16px;margin:32px 0 6px}
 .sub{color:#9a9aa5;margin:0 0 16px;max-width:70ch}
 .warn{color:#ffb4a2}
 .g{border:1px solid #2a2b33;border-radius:8px;padding:10px 12px;margin:0 0 10px;
    background:#191a20}
 .hd{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
 .nm{font-weight:600;word-break:break-all}
 .ct{color:#8f8f99;font-size:12px}
 .pill{font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid}
 .Personal{color:#9ad1ff;border-color:#2f5d80}
 .Communal{color:#ffd79a;border-color:#7a5c2a}
 .strip{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}
 .strip img{width:84px;height:84px;object-fit:cover;border-radius:4px;
            background:#22232b}
 .sj{color:#7f7f89;font-size:12px;margin-top:6px}
</style>
"""


def signature(path: str) -> str:
    """The device batch a filename belongs to: digit runs collapsed to #."""
    base = os.path.basename(path)
    base = os.path.splitext(base)[0]
    sig = DIGITS.sub("#", base)
    sig = re.sub(r"#+", "#", sig).strip(" _-.")
    return sig or "(no name)"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proposal", default=IN)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--thumbs", default=THUMBS)
    ap.add_argument("--per-group", type=int, default=10,
                    help="thumbnails shown per group")
    ap.add_argument("--max-groups", type=int, default=400,
                    help="groups rendered per side, largest first")
    a = ap.parse_args()

    if not os.path.exists(a.proposal):
        print("STOPPING: no proposal at {}".format(a.proposal))
        print("  Run propose_split_by_path.py first - reviewing a file that is")
        print("  not there would render an empty page that reads as 'nothing to")
        print("  check' rather than 'nothing was proposed'.")
        return 1

    rows = list(csv.DictReader(io.open(a.proposal, encoding="utf-8",
                                       newline="")))
    print("proposed moves: {:,}".format(len(rows)))
    assets = assets_for(a.thumbs) if os.path.isdir(a.thumbs) else {}
    print("hashes with a thumbnail: {:,}".format(len(assets)))

    groups: dict = collections.defaultdict(lambda: {
        "n": 0, "hashes": [], "years": set(), "kinds": collections.Counter(),
        "queues": collections.Counter(), "signals": collections.Counter()})
    for r in rows:
        key = (r["Side"], signature(r["Source"]))
        g = groups[key]
        g["n"] += 1
        g["kinds"][r.get("Kind") or "?"] += 1
        g["queues"][r.get("Queue") or "?"] += 1
        g["signals"][r.get("Signal") or "?"] += 1
        m = YEAR.search(r["Source"])
        if m:
            g["years"].add(m.group(1))
        h = r.get("Hash") or ""
        if h and h in assets and len(g["hashes"]) < a.per_group:
            g["hashes"].append(h)

    parts = [HEAD]
    parts.append("<h1>Proposed split &mdash; {:,} files in {:,} groups</h1>"
                 .format(len(rows), len(groups)))
    parts.append('<p class="sub">Nothing has moved. Judge the GROUP: a filename '
                 'batch is one device, so one question answers all of it. '
                 '<b>In Personal, look for anything that is plainly somebody '
                 "else's</b> - Personal is what a file gets by falling through, "
                 'so an unspotted family phone is sitting in your own '
                 'chronology. In Communal, look for anything that is actually '
                 'yours.</p>')

    for side in ("Communal", "Personal"):
        gs = sorted(((k[1], v) for k, v in groups.items() if k[0] == side),
                    key=lambda kv: -kv[1]["n"])
        total = sum(v["n"] for _, v in gs)
        parts.append("<h2>&rarr; {} &mdash; {:,} groups, {:,} files</h2>".format(
            side, len(gs), total))
        if side == "Communal":
            parts.append('<p class="sub">Every group shown. These matched '
                         '<code>bharti</code>, <code>bhasker</code> or '
                         '<code>Users\\Raja</code> somewhere in the path.</p>')
        else:
            parts.append('<p class="sub warn">Largest {} groups shown of {:,}. '
                         'These matched nothing and are Personal by default.</p>'
                         .format(min(a.max_groups, len(gs)), len(gs)))
        for name, v in gs[:a.max_groups]:
            ys = sorted(v["years"])
            span = "{}-{}".format(ys[0], ys[-1]) if ys else "no date"
            kinds = ", ".join("{} {}".format(n, k)
                              for k, n in v["kinds"].most_common(4))
            sig = ", ".join(s for s, _ in v["signals"].most_common(2))
            parts.append('<div class="g"><div class="hd">'
                         '<span class="nm">{}</span>'
                         '<span class="pill {}">{}</span>'
                         '<span class="ct">{:,} files &middot; {} &middot; {}'
                         '</span></div>'.format(
                             html.escape(name[:110]), side, side, v["n"],
                             span, html.escape(kinds)))
            if v["hashes"]:
                parts.append('<div class="strip">')
                for h in v["hashes"]:
                    src = assets[h][0].replace("\\", "/")
                    parts.append('<img loading="lazy" src="file:///{}">'.format(
                        html.escape(src)))
                parts.append("</div>")
            parts.append('<div class="sj">signal: {}</div></div>'.format(
                html.escape(sig)))

    io.open(a.out, "w", encoding="utf-8").write("".join(parts))
    print()
    print("wrote {}  ({:.1f} MB)".format(
        a.out, os.path.getsize(a.out) / 1048576))
    print("NOTHING HAS MOVED. This is a page to look at.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
