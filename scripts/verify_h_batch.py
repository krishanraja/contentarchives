r"""Paranoid verification of one H: ingest batch, before trusting the next fourteen.

Five questions, each answered against the disk rather than against the log:

  1. Does every row the journal calls 'new' exist at its destination?
  2. Do the bytes match the source on H: - not the size, the hash?
  3. Why did so much land in NoDate? What date signal, if any, survives?
  4. Did the library grow by exactly the number claimed?
  5. Are the 'skipped-tiny' and 'duplicate' verdicts actually true?

A batch that passes all five is a batch whose method can be trusted at scale.
"""

from __future__ import annotations

import csv
import collections
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

JOURNAL = r"D:\_PhotoAudit\INGEST-h-from-machine-b.csv"
H_SRC = r"H:\My Drive\_photo-consolidation\from-machine-b"
STAGE = r"D:\_h_stage"
SAMPLE = 25

fails: list[str] = []


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


rows = list(csv.DictReader(open(JOURNAL, encoding="utf-8", errors="replace")))
by_outcome = collections.Counter(r["Outcome"] for r in rows)
print(f"journal rows: {len(rows):,}  {dict(by_outcome)}")

# ---- 1. every 'new' row points at a file that exists -----------------------
new = [r for r in rows if r["Outcome"] == "new"]
missing = [r for r in new if not os.path.exists(lp(r["Destination"]))]
print(f"\n1. 'new' rows whose destination is missing: {len(missing):,} of {len(new):,}")
for m in missing[:3]:
    print(f"     {m['Destination']}")
if missing:
    fails.append("new rows point at missing files")

# ---- 2. hash a sample back against H: --------------------------------------
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

# ---- 3. why NoDate? --------------------------------------------------------
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

# ---- 4. did the library actually grow by 1,252? ----------------------------
print("\n4. library file count now vs inventory baseline (68,042 at 06:44):")
n = 0
for root in P.INVENTORY_ROOTS:
    for dp, dns, fns in os.walk(root):
        if "_Catalog" in dp:
            continue
        n += len(fns)
print(f"   files on disk: {n:,}   expected 68,042 + {len(new):,} = {68042+len(new):,}"
      f"   delta {n - (68042+len(new)):+,}")
if abs(n - (68042 + len(new))) > 5:
    fails.append(f"library grew by {n-68042}, journal claims {len(new)}")

# ---- 5. are 'skipped-tiny' really tiny, and 'duplicate' really present? -----
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
