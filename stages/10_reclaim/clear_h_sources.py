r"""Delete the consumed source folders from H:, keeping what is not proven held.

    python clear_h_sources.py
    python clear_h_sources.py --apply

Krish, 2026-09-18: *"feel free to clear photo consolidation"*, having said
earlier *"there are at least 2 copies of that content elsewhere"*.

WHAT IS PROVEN, AND WHAT IS NOT

`H:\My Drive\_photo-consolidation` holds 24,901 files / 501.5 GB and was the
SOURCE of the ingest. Checked against `ORIGIN-MAP.csv`, which records the origin
of every library file:

  22,103  traced by provenance - the library says, file by file, that it came
          from this exact path. That is evidence, not inference.
   1,830  a file of that exact size is in the library, but under another name.
     968  no match at all by provenance, name+size, or size.

So 88.8% is accounted for and 2,798 files / 42.7 GB are not. Those stay. Among
them: 144 `.lrf` and 123 `.lrv` camera proxies (27.6 GB, a sanctioned garbage
category but only where the full-resolution original sits beside them), and 283
`.mp4` files including `__v0`/`__v2` variant suffixes - which is exactly what
`video_variants.py` exists to reason about, warning that GoPro chapter names
look like duplicates and are not.

WHY THIS IS NOT guarded_delete

`guarded_delete` re-hashes victim and survivor at the instant of the unlink.
Here the victim is a Drive PLACEHOLDER: hashing it downloads it. Doing that for
495 GB would pull half a terabyte through a 131 GB cache, hydrating as it goes
(learning 5) - so the strongest available evidence is the origin map plus the
fact that Drive keeps a deleted file for 30 days. That is a weaker standard than
this project normally accepts, and it is recorded as such in the journal rather
than dressed up.

THE ORDER

Journal first, then delete, one file at a time, skipping anything whose size no
longer matches what the map described.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import io
import os
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401

import paths as P                                                 # noqa: E402

JOURNAL = os.path.join(P.AUDIT, "user-directed-deletions.csv")
KEEP = os.path.join(P.AUDIT, "H-SOURCE-NOT-HELD.csv")
REASON = ("user-directed clear of consumed H: sources (traced by ORIGIN-MAP "
          "provenance; Drive trash holds it 30 days)")


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=P.H_ROOT)
    ap.add_argument("--keep-list", default=KEEP,
                    help="files NOT proven held - these are never deleted")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        return int(bool(print("STOPPING: {} unreachable".format(a.root))))
    if not os.path.exists(a.keep_list):
        print("STOPPING: no {}.".format(a.keep_list))
        print("  Run verify_h_source_held first. Deleting without knowing which")
        print("  files are unproven is the whole thing this avoids.")
        return 1

    keep = set()
    with io.open(a.keep_list, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            p = (r.get("HPath") or "").strip()
            if p:
                keep.add(p.lower())
    print("not-proven-held, protected: {:,}".format(len(keep)))

    victims = []
    protected = 0
    for dp, dns, fns in os.walk(a.root):
        for fn in fns:
            p = os.path.join(dp, fn)
            if p.lower() in keep:
                protected += 1
                continue
            try:
                victims.append((p, os.path.getsize(p)))
            except OSError:
                continue

    gb = sum(s for _, s in victims) / (1 << 30)
    print("to delete                 : {:,} files   {:.1f} GB".format(
        len(victims), gb))
    print("protected by the keep list: {:,}".format(protected))

    print()
    print("=== by folder ===")
    byf = collections.Counter()
    bytesf = collections.Counter()
    for p, s in victims:
        rel = p[len(a.root):].lstrip("\\")
        top = rel.split("\\")[0] if "\\" in rel else "(root)"
        byf[top] += 1
        bytesf[top] += s
    for k, n in byf.most_common(12):
        print("  {:<52} {:>6,}  {:>7.1f} GB".format(
            k[:52], n, bytesf[k] / (1 << 30)))

    if not a.apply:
        print()
        print("DRY RUN - nothing deleted. Re-run with --apply.")
        return 0

    now = dt.datetime.now().isoformat(timespec="seconds")
    fresh = not os.path.exists(JOURNAL)
    deleted = freed = failed = 0
    with io.open(JOURNAL, "a", encoding="utf-8", newline="") as jf:
        w = csv.writer(jf)
        if fresh:
            w.writerow(["Path", "Bytes", "Reason", "Evidence", "When"])
        for i, (p, s) in enumerate(victims, 1):
            try:
                if os.path.getsize(p) != s:
                    print("  size changed, keeping: {}".format(p[-70:]))
                    continue
            except OSError:
                continue
            w.writerow([p, s, REASON,
                        "ORIGIN-MAP traces this path into the library; "
                        "not in H-SOURCE-NOT-HELD.csv", now])
            try:
                os.remove(lp(p))
            except OSError as e:
                failed += 1
                print("  delete failed {}: {}".format(p[-60:], e))
                continue
            deleted += 1
            freed += s
            if deleted % 500 == 0:
                jf.flush()
                os.fsync(jf.fileno())
                print("  {:,}/{:,}  {:.1f} GB freed".format(
                    i, len(victims), freed / (1 << 30)), flush=True)
        jf.flush()
        os.fsync(jf.fileno())

    print()
    print("deleted {:,} files, freed {:.1f} GB, failed {:,}".format(
        deleted, freed / (1 << 30), failed))
    print("kept {:,} files that were not proven held - see {}".format(
        protected, a.keep_list))
    print()
    print("Google Drive holds deleted files in its own trash for 30 days.")
    print("That is the undo, and emptying that trash is a separate, manual act.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
