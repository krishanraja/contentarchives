r"""Check the router against folders whose character is already known.

Ground truth established by survey and by inspecting from-machine-b after ingest:

  from-dji-2026 / from-gopro-2024   pure camera dumps  -> ~100% chronology
  from-machine-b                      ~90% QA + Downloads -> mostly production
  user - Phone Backup              camera + Downloads PDFs + hypnosis audio
                                                        -> mixed, all three

A classifier that cannot reproduce a known answer is not ready for 24,000
unknown files. This prints the distribution per folder and samples each
decision so the reasoning is visible, not just the totals.

IT WAS BROKEN AND NOTHING NOTICED, which is the more useful thing this file now
records. It reached its imports with

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from route_h import route

- its own directory only. route_h.py moved into stages/02_ingest/ on 2026-09-16
and that import could no longer resolve. It went unnoticed because this script
ran its whole body at module level, so tests/test_imports.py refused to import
it and never exercised the import at all: the file was outside the net that
would have caught it in seconds. Hence the stagepath walk-up below, which finds
a stage wherever the conveyor has put it, and a main() so the sweep can import
this module without running a survey of a cloud mount.
"""

from __future__ import annotations

import collections
import os
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
from route_h import route                                        # noqa: E402
from survey_h_folders import H_ROOT, NEVER                       # noqa: E402

SKIP = {"_audit-trail", "in", "out"}


def main() -> None:
    if not os.path.isdir(H_ROOT):
        sys.exit(f"no such source root: {H_ROOT}")

    for folder in sorted(os.listdir(H_ROOT)):
        root = os.path.join(H_ROOT, folder)
        if not os.path.isdir(root) or folder in SKIP:
            continue
        counts: collections.Counter = collections.Counter()
        gb: collections.Counter = collections.Counter()
        samples: dict[str, list[str]] = collections.defaultdict(list)
        for dp, dns, fns in os.walk(root):
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in NEVER:
                    continue
                p = os.path.join(dp, fn)
                try:
                    sz = os.path.getsize(p)
                except OSError:
                    continue
                if sz == 0:
                    continue
                rel = os.path.relpath(p, root)
                d, why = route(rel)
                counts[d] += 1
                gb[d] += sz
                if len(samples[d]) < 3:
                    samples[d].append(f"[{why}] {rel[:74]}")
        tot = sum(counts.values())
        print(f"\n=== {folder}   ({tot:,} files)")
        for d in ("chronology", "production", "archive"):
            if counts[d]:
                print(f"  {d:<11} {counts[d]:>6,}  {counts[d]*100/tot:>5.1f}%  "
                      f"{gb[d]/1024**3:>7.1f} GB")
                for s in samples[d]:
                    print(f"       {s}")


if __name__ == "__main__":
    main()
