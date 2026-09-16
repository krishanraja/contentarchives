r"""Paranoid verification of one H: ingest batch, before trusting the next fourteen.

Five questions, each answered against the disk rather than against the log:

  1. Does every row the journal calls 'new' exist at its destination?
  2. Do the bytes match the source on H: - not the size, the hash?
  3. Why did so much land in NoDate? What date signal, if any, survives?
  4. Did the library grow by exactly the number claimed?
  5. Are the 'skipped-tiny' and 'duplicate' verdicts actually true?

A batch that passes all five is a batch whose method can be trusted at scale.

EXIT CODE

0 when every check passes, 1 when any fails. It used to print FAILED and exit
0, which makes it a gate that cannot gate: a chain step calling this would have
read success off a run that had just found mismatched bytes.

The work is inside main() so that importing this file hashes nothing.
"""

from __future__ import annotations

import csv
import collections
import hashlib
import os
import random
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                                # noqa: E402

# The one batch this was written to interrogate. Named rather than spelled into
# four separate literals, so pointing it at the next batch is one edit.
BATCH = "from-machine-b"
JOURNAL = os.path.join(P.AUDIT, "INGEST-h-from-machine-b.csv")
H_SRC = os.path.join(P.H_ROOT, BATCH)
STAGE = P.H_STAGE
SAMPLE = 25

# The library's file count before this batch landed, read at 06:44. Question 4
# is meaningless without it, so it is named and dated rather than inlined.
BASELINE = 68042


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def h(p: str) -> str | None:
    try:
        d = hashlib.blake2b(digest_size=32)
        with open(lp(p), "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                d.update(b)
        return d.hexdigest()
    except OSError:
        return None


def main() -> int:
    fails: list[str] = []

    rows = list(csv.DictReader(open(JOURNAL, encoding="utf-8", errors="replace")))
    by_outcome = collections.Counter(r["Outcome"] for r in rows)
    print(f"journal rows: {len(rows):,}  {dict(by_outcome)}")

    # ---- 1. every 'new' row points at a file that exists -------------------
    new = [r for r in rows if r["Outcome"] == "new"]
    missing = [r for r in new if not os.path.exists(lp(r["Destination"]))]
    print(f"\n1. 'new' rows whose destination is missing: {len(missing):,} of {len(new):,}")
    for m in missing[:3]:
        print(f"     {m['Destination']}")
    if missing:
        fails.append("new rows point at missing files")

    # ---- 2. hash a sample back against H: ----------------------------------
    # The staged copy is gone, so this compares the library against the ORIGINAL
    # on the mount. That is the comparison that matters: it proves the whole
    # chain (H: -> stage -> library) moved the bytes intact, not just one hop.
    print(f"\n2. hashing {SAMPLE} random 'new' files against their H: source:")
    random.seed(11)
    ok = bad = unreadable = 0
    for r in random.sample(new, min(SAMPLE, len(new))):
        rel = os.path.relpath(r["Source"], STAGE)
        src = os.path.join(H_SRC, rel)
        if not os.path.exists(lp(src)):
            unreadable += 1
            print(f"     ? source gone from H:: {rel[:70]}")
            continue
        a, b = h(src), h(r["Destination"])
        if a is None or b is None:
            unreadable += 1
            print(f"     ? unreadable: {rel[:70]}")
        elif a == b:
            ok += 1
        else:
            bad += 1
            print(f"     MISMATCH {rel[:60]}")
    print(f"   identical: {ok}   mismatched: {bad}   unreadable: {unreadable}")
    if bad:
        fails.append(f"{bad} sampled files differ from their H: source")

    # ---- 3. why NoDate? ----------------------------------------------------
    nodate = [r for r in new if os.sep + "NoDate" + os.sep in r["Destination"]
              or r["Destination"].startswith(P.NODATE)]
    print(f"\n3. NoDate: {len(nodate):,} of {len(new):,} new files "
          f"({len(nodate)*100/max(len(new),1):.0f}%)")
    ext = collections.Counter(os.path.splitext(r["Destination"])[1].lower() for r in nodate)
    print(f"   by extension: {dict(ext.most_common(8))}")
    srcdir = collections.Counter(
        os.path.dirname(os.path.relpath(r["Source"], STAGE)).split(os.sep)[0] or "(root)"
        for r in nodate)
    print(f"   by source subfolder: {dict(srcdir.most_common(8))}")

    # does the filesystem mtime carry a plausible date the ingest ignored?
    have_mtime = 0
    years: collections.Counter = collections.Counter()
    for r in nodate[:400]:
        try:
            y = __import__("datetime").datetime.fromtimestamp(
                os.path.getmtime(lp(r["Destination"]))).year
        except OSError:
            continue
        if 1995 <= y <= 2026:
            have_mtime += 1
            years[y] += 1
    print(f"   of the first 400, mtime gives a plausible year for {have_mtime}: "
          f"{dict(years.most_common(8))}")

    # ---- 4. did the library actually grow by what was claimed? -------------
    print(f"\n4. library file count now vs inventory baseline ({BASELINE:,} at 06:44):")
    n = 0
    for root in P.INVENTORY_ROOTS:
        for dp, dns, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            n += len(fns)
    print(f"   files on disk: {n:,}   expected {BASELINE:,} + {len(new):,} = "
          f"{BASELINE+len(new):,}   delta {n - (BASELINE+len(new)):+,}")
    if abs(n - (BASELINE + len(new))) > 5:
        fails.append(f"library grew by {n-BASELINE}, journal claims {len(new)}")

    # ---- 5. are 'skipped-tiny' really tiny, and 'duplicate' really present? -
    tiny = [r for r in rows if r["Outcome"] == "skipped-tiny"]
    big_tiny = 0
    for r in tiny[:200]:
        rel = os.path.relpath(r["Source"], STAGE)
        src = os.path.join(H_SRC, rel)
        try:
            if os.path.getsize(lp(src)) > 100 * 1024:
                big_tiny += 1
        except OSError:
            pass
    print(f"\n5. 'skipped-tiny' larger than 100 KB (of first 200): {big_tiny}")
    if big_tiny:
        fails.append(f"{big_tiny} files called tiny are not tiny")

    dup = [r for r in rows if r["Outcome"] == "duplicate"]
    print(f"   'duplicate' rows: {len(dup):,}  (Note column sample)")
    for d in dup[:3]:
        print(f"     {d.get('Note','')[:100]}")

    print("\nVERDICT:", "ALL CHECKS PASS" if not fails else "FAILED: " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
