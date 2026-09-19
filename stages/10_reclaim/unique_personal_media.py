r"""Of everything found ONLY outside the library, what is genuinely personal?

    python unique_personal_media.py

Krish, 2026-09-19: *"I dont care about work media and screen shots, I want to
know that no completely new and definitely personal or communal content has been
left behind before we are 100% confident to purge where everything came from"*.

That is a narrower question than "what is unique", and the difference is the
whole point. `audit_source_tree.py` proves whether the library holds a file's
exact bytes. A UNIQUE verdict only means "the library does not hold this" - it
says nothing about whether anyone would ever want it. Most uniques are a work
laptop's screenshots, a `node_modules` staging folder, or a phone's thumbnail
cache, and reporting those alongside a missing photograph of a person buries the
one thing that matters in 1,400 things that do not.

So this reads every SOURCE-AUDIT-*.csv, takes the UNIQUE rows, and splits them:

  KEEP-CANDIDATE - plausibly a real personal or communal photograph or video,
                   and therefore content that would be LOST if its source were
                   purged;
  NOISE          - screenshots, work material, caches, thumbnails, build
                   artefacts, and files whose extension only looks like media.

THE .mts TRAP, which is why extensions alone cannot decide this. `.mts` is
AVCHD video from a camcorder AND the TypeScript module extension. OneDrive's
audit counted 654 "videos" that are TypeScript source files inside a
`node_modules` staging directory. An extension list is a filter, never a
classification.

BIASED TOWARDS KEEPING. Every rule here decides what to IGNORE, and anything
not positively recognised as noise stays a keep-candidate. A false keep costs a
human thirty seconds of review; a false ignore silently destroys the only copy
of a photograph. Those are not symmetric, so the doubt goes one way.

Read-only. Writes a review list and deletes nothing.
"""

from __future__ import annotations

import collections
import csv
import glob
import io
import os
import re
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402

OUT = os.path.join(P.AUDIT, "UNIQUE-PERSONAL-REVIEW.csv")

csv.field_size_limit(1 << 30)

# Path fragments that mean "nobody is going to miss this". Lower-case.
NOISE_PATH = (
    "screenshot", "screen shot", "\\.thumbnails", "thumbnail", "\\cache",
    "\\appdata\\", "node_modules", "\\temp\\", "\\tmp\\", "webpack",
    "\\icons\\", "\\_swaami", "staging", "captify", "adfixus", "\\work ",
    "work backup", "\\fractionl", "\\mindmaker", "\\ventures\\",
    "\\documents\\0 ventures", "\\program files", "\\windows\\",
    "\\downloads\\inbox", "favicon", "\\logs\\", "\\.git\\",
)

# Extensions that are media by name only in some contexts.
AMBIGUOUS = {".mts"}

# A filename that looks like it came out of a camera or a phone.
CAMERA_RX = re.compile(
    r"(^|[^a-z0-9])("
    r"img[-_ ]?\d|dsc[fn]?\d|dscn\d|vid[-_]\d|mvimg|pano|"
    r"dji[-_]\d|gh\d{6}|gx\d{6}|gopr\d|g\d{7}|"
    r"pxl[-_]\d|wa\d{4}|mah\d|"
    r"\d{8}[-_]\d{6}|\d{4}-\d{2}-\d{2}"
    r")", re.I)

# Folders that say "this was already treated as library content".
LIBRARY_HINT = ("\\contentlibrary\\", "\\media\\personal\\",
                "\\media\\communal\\", "\\_review\\",
                "\\pending-segmentation\\", "\\dcim\\", "\\camera\\",
                "\\whatsapp\\", "\\photos\\", "\\pictures\\")


def classify(path: str, size: int) -> tuple[str, str]:
    low = path.lower()
    ext = os.path.splitext(low)[1]

    for frag in NOISE_PATH:
        if frag in low:
            return "NOISE", "path contains '{}'".format(frag.strip("\\"))

    if ext in AMBIGUOUS and "node_modules" not in low:
        # .mts outside a source tree could be real camcorder footage, so it is
        # only noise where the surrounding path says otherwise.
        if not any(h in low for h in LIBRARY_HINT):
            return "NOISE", "ambiguous extension outside any media folder"

    base = os.path.basename(low)
    in_lib = any(h in low for h in LIBRARY_HINT)
    looks_camera = bool(CAMERA_RX.search(base))

    if in_lib or looks_camera:
        return "KEEP-CANDIDATE", ("inside a media folder" if in_lib
                                  else "camera-style filename")

    # Not recognised either way. Doubt goes towards keeping.
    return "KEEP-CANDIDATE", "unclassified - kept for review by default"


def main() -> int:
    files = sorted(glob.glob(os.path.join(P.AUDIT, "SOURCE-AUDIT-*.csv")))
    if not files:
        print("no SOURCE-AUDIT-*.csv found - run audit_source_tree.py first")
        return 1

    rows = []
    per_source = collections.Counter()
    for f in files:
        src = os.path.basename(f)
        for r in csv.DictReader(io.open(f, encoding="utf-8", newline="")):
            if r.get("Verdict") != "UNIQUE":
                continue
            try:
                size = int(r.get("Bytes") or 0)
            except ValueError:
                size = 0
            verdict, why = classify(r["Path"], size)
            rows.append((verdict, size, r["Path"], why, src))
            per_source[(src, verdict)] += 1

    keep = [r for r in rows if r[0] == "KEEP-CANDIDATE"]
    noise = [r for r in rows if r[0] == "NOISE"]
    keep.sort(key=lambda t: -t[1])

    print("UNIQUE files across every audited source: {:,}".format(len(rows)))
    print()
    print("  NOISE (screenshots, work, caches, build output) : {:>6,}  {:>7.2f} GB".format(
        len(noise), sum(r[1] for r in noise) / (1 << 30)))
    print("  KEEP-CANDIDATE (possibly real personal media)   : {:>6,}  {:>7.2f} GB".format(
        len(keep), sum(r[1] for r in keep) / (1 << 30)))
    print()

    print("by source:")
    for f in files:
        src = os.path.basename(f)
        k = per_source[(src, "KEEP-CANDIDATE")]
        n = per_source[(src, "NOISE")]
        if k or n:
            print("  {:<44} keep {:>5,}   noise {:>5,}".format(src[:44], k, n))
    print()

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Verdict", "Bytes", "Path", "Why", "Source"])
        for r in keep + noise:
            w.writerow(r)
        fh.flush()
        os.fsync(fh.fileno())
    print("full list: {}".format(OUT))
    print()

    print("THE ONES THAT WOULD BE LOST - largest 30 keep-candidates:")
    for verdict, size, path, why, src in keep[:30]:
        print("  {:>8.1f} MB  {}".format(size / (1 << 20), path[-92:]))

    print()
    big = [r for r in keep if r[1] > 2 * (1 << 20)]
    print("keep-candidates over 2 MB (most likely to be real): {:,}  {:.2f} GB".format(
        len(big), sum(r[1] for r in big) / (1 << 30)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
