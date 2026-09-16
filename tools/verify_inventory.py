r"""Re-probe a few videos and check the inventory recorded what is actually there.

    python verify_inventory.py --sample 4      # 0 correct, 1 wrong, 2 can't tell

WHY

build_inventory ran for 33 minutes on 2026-09-12 and wrote no Duration, Width or
Height for any of 12,988 videos, because ffprobe was looked for under another
machine's username and a missing binary returned an empty dict. It exited 0. The
CSV was complete and well-formed. Only counting a column afterwards found it.

Checking the shape of INVENTORY.csv cannot catch that, because the shape was
never wrong. So this asks ffprobe again, for files the pass claims to have
already measured, and compares the answer.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

import os as _os, sys as _sys                                    # noqa: E402
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - resolves a script wherever the conveyor put it

# Without this, stagepath.script() below is a NameError. It did not show up in a
# compile check or an import check, because the call sits inside a function body
# that neither one executes - the same half-finished edit made in runner.py an
# hour earlier. "It imported fine" is not "it works" (learning 54).


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", default=r"D:\_PhotoAudit\INVENTORY.csv")
    ap.add_argument("--sample", type=int, default=4)
    a = ap.parse_args()

    if not os.path.exists(a.inventory):
        print("verify: no inventory yet")
        return 2

    spec = importlib.util.spec_from_file_location(
        "bi", stagepath.script("build_inventory.py"))
    bi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bi)
    if not bi.FFPROBE or not os.path.exists(bi.FFPROBE):
        print("verify: ffprobe is not resolvable - videos cannot be measured")
        return 1

    vids = []
    with io.open(a.inventory, encoding="utf-8", errors="replace",
                 newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("Kind") or "") == "video" and (r.get("Duration") or "").strip():
                vids.append(r)
    if len(vids) < 3:
        print("verify: only {} measured videos so far".format(len(vids)))
        return 2

    random.shuffle(vids)
    checked = bad = 0
    for r in vids[:a.sample]:
        p = r["LibraryPath"]
        if not os.path.exists(p):
            continue
        got = bi.probe_video(p)
        checked += 1
        want = float(r["Duration"])
        have = got.get("Duration")
        if have is None:
            bad += 1
            print("  {}  re-probe returned no duration".format(os.path.basename(p)[:44]))
        elif abs(float(have) - want) > max(1.0, want * 0.02):
            bad += 1
            print("  {}  stored {:.1f}s, actual {:.1f}s".format(
                os.path.basename(p)[:44], want, float(have)))
    if checked == 0:
        print("verify: none of the sampled videos could be re-probed")
        return 2
    print("verify: re-probed {} videos, {} disagreed".format(checked, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
