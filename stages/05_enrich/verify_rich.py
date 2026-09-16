r"""Check the description pass is writing DESCRIPTIONS, not labels.

    python verify_rich.py --sample 25     # 0 correct, 1 wrong, 2 can't tell

WHY THIS SPECIFIC CHECK

`call()` in classify_live.py read the prompt from a module-level global. The
--rich switch chose a different prompt in main() and passed it nowhere. Had that
shipped, the rich pass would have sent the OLD five-word prompt, parsed the old
answer, and stored it under the rich source id with the rich field names: a
complete, plausible, $46 result whose "description" column contained four-word
labels. Every count would have been right. Every row would have been present.
The exit code would have been 0.

So the check is not "did rows appear" but "are the values the SHAPE a
description has". A label is four words. A description is a sentence. Nothing
else distinguishes the correct run from the expensive wrong one.

It also insists the other fields are being populated, because a prompt that half
works - returning description but never objects or text - is the same failure
wearing a smaller hat.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
MIN_WORDS = 15          # a label is 4; a sentence is 20+; 15 is generous
MIN_FILLED = 0.35       # at least this share should carry objects/activity


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", default=r"D:\_enrichment\content_tags.csv")
    ap.add_argument("--sample", type=int, default=25)
    ap.add_argument("--suffix", default="-rich")
    a = ap.parse_args()

    by = collections.OrderedDict()
    try:
        with io.open(a.tags, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                if (r.get("source") or "").endswith(a.suffix):
                    by.setdefault(r["hash"], {})[r.get("tag")] = r.get("value", "")
    except FileNotFoundError:
        print("verify: no tag store yet")
        return 2

    if len(by) < 5:
        print("verify: only {} described files so far".format(len(by)))
        return 2

    # the newest are what a running pass is producing right now
    recent = list(by.values())[-a.sample:]
    descs = [v.get("description", "") for v in recent]
    lens = [len(d.split()) for d in descs if d]
    if not lens:
        print("verify: {} recent files and NOT ONE has a description".format(len(recent)))
        return 1

    short = sum(1 for n in lens if n < MIN_WORDS)
    med = sorted(lens)[len(lens) // 2]
    objs = sum(1 for v in recent if (v.get("objects") or "").strip())
    acts = sum(1 for v in recent if (v.get("activity") or "").strip())

    print("verify: {} recent described files, median {} words".format(len(recent), med))
    print("        {} of {} shorter than {} words".format(short, len(lens), MIN_WORDS))
    print("        objects on {:.0f}%, activity on {:.0f}%".format(
        100.0 * objs / len(recent), 100.0 * acts / len(recent)))

    if med < MIN_WORDS:
        print("        FAIL: these are labels, not descriptions - is the rich "
              "prompt actually being sent?")
        return 1
    if objs < len(recent) * MIN_FILLED and acts < len(recent) * MIN_FILLED:
        print("        FAIL: description present but the other fields are empty "
              "- the prompt is only half working")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
