r"""PURGED-HASHES.csv: content destroyed on purpose, never to come back anywhere.

One reader for every consumer. It lived inside stages/02_ingest/autopilot.py,
whose import walks the library index; the archives app needs the same list
(a purged photograph must never be uploaded to the family app either) without
that cost, and two readers of one ledger is how one of them stops honouring
learning 60's malformed rows.

    from blocklist import read_blocklist, blocked_hashes
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict

import paths as P

BLOCKLIST = os.path.join(P.AUDIT, "PURGED-HASHES.csv")


def read_blocklist(path: str = BLOCKLIST):
    """({size: {hash}}, malformed rows, present).

    A missing list is EMPTY and says so through `present`: "no file" and "no
    entries" must never look the same as a working list that matches nothing.
    A size in the Hash column is what a broken writer produced once (learning
    60) - counted, never trusted.
    """
    out = defaultdict(set)
    if not os.path.exists(path):
        return out, 0, False
    bad = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].strip().lower() in ("hash", ""):
                continue
            h = row[0].strip().lower()
            if len(h) != 64:
                bad += 1
                continue
            size = int(row[1]) if len(row) > 1 and str(row[1]).isdigit() else -1
            out[size].add(h)
    return out, bad, True


def blocked_hashes(path: str = BLOCKLIST) -> set:
    """Every purged hash, sizes ignored. Announces an absent list."""
    idx, bad, present = read_blocklist(path)
    if not present:
        print("  no-reingest list ABSENT at {} - nothing is blocked".format(path))
    if bad:
        print("  WARNING: {} blocklist row(s) have no 64-hex hash - IGNORED".format(bad))
    return set().union(*idx.values()) if idx else set()
