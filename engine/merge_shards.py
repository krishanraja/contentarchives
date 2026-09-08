r"""Merge per-worker store shards into one store.

Parallel workers each write their own store because the store's lock is
per-process: six processes appending to one CSV can interleave a row and
corrupt it silently. Sharding avoids that entirely, and merging is safe because
every file in the store is APPEND-ONLY - there are no updates to reconcile and
no ordering that matters beyond the timestamp already on each row.

The one thing that needs care is person ids. Each shard numbers people from 1
independently, so shard 0's "Person 3" and shard 3's "Person 3" are different
people. Ids are therefore REBASED per shard on merge, and observations are
rewritten to match. Merging without that would silently fuse strangers, which
is the one error in this system that a human would find hard to spot later.

    python merge_shards.py --store D:\_enrichment
"""

from __future__ import annotations

import argparse
import csv
import os


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    a = ap.parse_args()

    shards = sorted(d for d in os.listdir(a.store)
                    if d.startswith("shard-") and
                    os.path.isdir(os.path.join(a.store, d)))
    print(f"merging {len(shards)} shards")

    offset = 0
    merged: dict[str, list] = {}
    headers: dict[str, list] = {}

    for sh in shards:
        d = os.path.join(a.store, sh)
        remap: dict[str, str] = {}

        pf = os.path.join(d, "people.csv")
        max_id = 0
        if os.path.exists(pf):
            with open(pf, newline="", encoding="utf-8", errors="replace") as f:
                r = csv.reader(f)
                headers.setdefault("people.csv", next(r, []))
                for row in r:
                    if not row:
                        continue
                    old = row[0]
                    new = str(int(old) + offset)     # rebase so ids stay unique
                    remap[old] = new
                    row[0] = new
                    if row[1].startswith("Person "):
                        row[1] = f"Person {new}"
                    merged.setdefault("people.csv", []).append(row)
                    max_id = max(max_id, int(old))

        for name, idcol in (("content_tags.csv", None),
                            ("observations.csv", 1),
                            ("merge_suggestions.csv", None),
                            ("files.csv", None)):
            p = os.path.join(d, name)
            if not os.path.exists(p):
                continue
            with open(p, newline="", encoding="utf-8", errors="replace") as f:
                r = csv.reader(f)
                headers.setdefault(name, next(r, []))
                for row in r:
                    if not row:
                        continue
                    if idcol is not None and len(row) > idcol and row[idcol] in remap:
                        row[idcol] = remap[row[idcol]]
                    if name == "merge_suggestions.csv":
                        for i in (0, 1):
                            if len(row) > i and row[i] in remap:
                                row[i] = remap[row[i]]
                    merged.setdefault(name, []).append(row)
        offset += max_id
        print(f"  {sh}: person ids rebased by +{offset - max_id}")

    for name, rows in merged.items():
        out = os.path.join(a.store, name)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if headers.get(name):
                w.writerow(headers[name])
            w.writerows(rows)
        print(f"  {name:<26} {len(rows):>8,} rows")
    print(f"\nmerged into {a.store}")


if __name__ == "__main__":
    main()
