r"""A size index of the WHOLE library, built from the disk, every time.

lib-hashes.csv held 19,853 rows against a library of 69,294 files - 29% - and
nothing about it said so. Anything asking it "have I seen this size?" got a
confident 'no' for 71% of the library.

This walks the real roots and writes what it finds, plus the count, so a reader
can check coverage against the library instead of trusting the file's name.
Sizes only: os.walk and stat read directory metadata and open nothing.
"""

from __future__ import annotations

import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

OUT = r"D:\_PhotoAudit\lib-size-index.csv"


def build() -> collections.Counter:
    sizes: collections.Counter = collections.Counter()
    n = 0
    for root in P.INVENTORY_ROOTS:
        for dp, dns, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                try:
                    sizes[os.path.getsize(os.path.join(dp, fn))] += 1
                except OSError:
                    continue
                n += 1
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Bytes", "Count"])
        for s, c in sorted(sizes.items()):
            w.writerow([s, c])
    print(f"indexed {n:,} files, {len(sizes):,} distinct sizes -> {OUT}")
    return sizes


if __name__ == "__main__":
    build()
