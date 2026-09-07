r"""Move Google's re-compressed copies out of the chronology, keep the originals.

Google Photos returns "Storage saver" re-encodings of media you uploaded at full
quality. They are not byte-identical to the originals, so the content-hash dedup
correctly calls them new and files them - and the library gains a second, worse
copy of a photo it already had. Measured on Takeout part 001: 1,123 such files,
quality gaps reaching 66.8x (a 1.4 MB clip against a 90.2 MB original).

The dedup is not broken. Its specification simply does not cover "same
photograph, worse encoding", because that is a judgement about quality rather
than about bytes.

WHAT THIS DOES

Fresh ingest lands in `Library\`, not in the chronology, which is what makes this
fixable at all. For each file there, it looks for a same-named file already in
the established chronology (`Personal\`, `Communal\`, `NoDate\`) of a different
size:

  archive copy SMALLER  -> the degraded duplicate. MOVED to `_Review\`.
  archive copy LARGER   -> the opposite case, and valuable: the library is
                           holding a truncated or lesser copy. REPORTED, never
                           moved - replacing an original is the user's call.

Nothing is ever deleted. A classifier may move a file; it may not delete one.
`_Review\` is a holding area the user empties, so a wrong call here costs a look,
not a photograph.

THE HUGE-FILE FLAG

Where the original being kept is very large (--huge, default 1 GB) it is listed
separately. The instruction is to keep originals, but a 2 GB retained file is a
decision worth seeing rather than one made silently on your behalf.

WHY A SIZE RATIO GUARD

Same basename is evidence, not proof: GoPro reuses names like `gh010947.mp4`
across cards, so two genuinely different clips can collide. A large size ratio
makes the re-encode reading far more likely than the coincidence one, so pairs
closer than --min-ratio are reported rather than moved. Every pair carries its
ratio into the journal so a human can second-guess any of them.

    python triage_downgrades.py                 # report only
    python triage_downgrades.py --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import sys
from collections import defaultdict

LIBROOT = r"D:\PhotoLibrary"
NEW = os.path.join(LIBROOT, "Library")
CHRONOLOGY = [os.path.join(LIBROOT, d) for d in ("Personal", "Communal", "NoDate")]
REVIEW = os.path.join(LIBROOT, "_Review")
MANIFEST = os.path.join(LIBROOT, "_Catalog", "manifest.csv")
JOURNAL = r"D:\_PhotoAudit\downgrade-triage.csv"
REPORT = r"D:\_PhotoAudit\DOWNGRADE-TRIAGE-REPORT.csv"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def walk(root: str):
    for dp, _, fns in os.walk(lp(root)):
        for fn in fns:
            full = os.path.join(dp, fn).replace("\\\\?\\", "")
            try:
                yield full, os.path.getsize(lp(full))
            except OSError:
                continue


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--huge", type=float, default=1.0,
                   help="flag a retained original larger than this many GB (default 1)")
    p.add_argument("--min-ratio", type=float, default=1.10,
                   help="only move when the original is at least this many times "
                        "bigger (default 1.10)")
    a = p.parse_args()

    if not os.path.isdir(lp(NEW)):
        sys.exit(f"no such folder: {NEW}")

    print("indexing the established chronology...")
    held: dict[str, list[tuple[str, int]]] = defaultdict(list)
    n_held = 0
    for root in CHRONOLOGY:
        if not os.path.isdir(lp(root)):
            continue
        for full, size in walk(root):
            held[os.path.basename(full).lower()].append((full, size))
            n_held += 1
    print(f"  {n_held:,} files, {len(held):,} distinct basenames")

    downgrades, upgrades, ambiguous = [], [], []
    n_new = 0
    for full, size in walk(NEW):
        n_new += 1
        cands = held.get(os.path.basename(full).lower())
        if not cands:
            continue
        # compare against the largest copy already held
        best_path, best_size = max(cands, key=lambda t: t[1])
        if size == best_size:
            continue                      # same size: dedup already had its say
        if size < best_size:
            ratio = best_size / max(size, 1)
            row = (full, size, best_path, best_size, ratio)
            (downgrades if ratio >= a.min_ratio else ambiguous).append(row)
        else:
            upgrades.append((full, size, best_path, best_size, size / max(best_size, 1)))

    GB = 1024 ** 3
    print(f"\nscanned {n_new:,} files in {NEW}")
    print(f"  degraded duplicates to move : {len(downgrades):,} "
          f"({sum(r[1] for r in downgrades)/GB:.2f} GB)")
    print(f"  too close to call (kept)    : {len(ambiguous):,}")
    print(f"  BETTER than what is held    : {len(upgrades):,}  <- review these")

    huge = [r for r in downgrades if r[3] >= a.huge * GB]
    if huge:
        print(f"\n  originals being kept that exceed {a.huge:g} GB: {len(huge):,}")
        for _, _, bp, bs, _ in sorted(huge, key=lambda r: -r[3])[:10]:
            print(f"      {bs/GB:6.2f} GB  {os.path.basename(bp)}")

    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Verdict", "NewFile", "NewBytes", "HeldFile", "HeldBytes",
                    "Ratio", "RetainedOriginalHuge"])
        for tag, rows in (("downgrade-move", downgrades),
                          ("too-close-kept", ambiguous),
                          ("upgrade-review", upgrades)):
            for np_, ns, hp, hs, ratio in rows:
                w.writerow([tag, np_, ns, hp, hs, f"{ratio:.2f}",
                            "yes" if hs >= a.huge * GB else ""])
    print(f"\nreport: {REPORT}")

    if not a.apply:
        print("\nReport only. Re-run with --apply to move the degraded duplicates.")
        return

    os.makedirs(lp(REVIEW), exist_ok=True)
    moved: dict[str, str] = {}
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    with open(JOURNAL, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if jf.tell() == 0:
            w.writerow(["When", "From", "To", "Bytes", "KeptOriginal",
                        "KeptBytes", "Ratio"])
        for np_, ns, hp, hs, ratio in downgrades:
            rel = os.path.relpath(np_, LIBROOT)
            dest = os.path.join(REVIEW, rel)
            os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
            stem, ext = os.path.splitext(dest)
            k = 0
            while os.path.exists(lp(dest)):
                k += 1
                dest = f"{stem}__{k}{ext}"
            try:
                shutil.move(lp(np_), lp(dest))
                moved[np_] = dest
                w.writerow([stamp, np_, dest, ns, hp, hs, f"{ratio:.2f}"])
            except OSError as e:
                print(f"  FAILED {np_}: {e}")
        jf.flush()
        os.fsync(jf.fileno())

    # the journal is durable before the manifest is touched
    out = []
    with open(MANIFEST, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.reader(f):
            if r and r[0] in moved:
                r[0] = moved[r[0]]
            out.append(r)
    tmp = MANIFEST + ".new"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    os.replace(tmp, MANIFEST)

    print(f"\nmoved {len(moved):,} files to {REVIEW}; manifest updated")
    print(f"journal: {JOURNAL}")
    print("Nothing was deleted. Review and empty _Review yourself.")


if __name__ == "__main__":
    main()
