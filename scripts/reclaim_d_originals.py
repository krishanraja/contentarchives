r"""Classify every file on D: outside the library: redundant, hardlinked, or ONLY.

D: holds ~356 GB outside ContentLibrary - the source folders the library was
built from. The user authorised clearing the ones proven safe inside the
library. "Proven" is the whole job, and there are three outcomes, not two:

  RECLAIMABLE  a library copy exists at a DIFFERENT inode with identical bytes.
               Deleting frees real space.

  HARDLINK     a library path holds the same bytes because it is the same
               bytes - one file, two names. Deleting the source is harmless
               but frees NOTHING. Counting these as reclaim is how a previous
               pass predicted 300 GB that did not exist.

  ONLY         no library copy. This file is the only version. It is never
               deleted; it is queued for ingest. The disk is the source of
               truth - a file missing from the library means the library is
               incomplete, not that the file is surplus.

This script only WRITES THE CLASSIFICATION. Deleting is a separate step, done
through guarded_delete, which re-verifies everything from the filesystem again
at the moment of the unlink. A report is never evidence.

    python reclaim_d_originals.py                 # full measurement
    python reclaim_d_originals.py --limit 500     # -> a .sample500.csv, never the real one
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402

OUT = r"D:\_PhotoAudit\D-ORIGINALS-STATUS.csv"
# _thumbs and _enrichment are this project's own derived output. Counting them
# as "files that exist nowhere in the library" was true and useless: it put
# 15,794 generated thumbnails at the top of a list of the user's orphaned
# content.
EXCLUDE_TOP = {"contentlibrary", "_photoaudit", "$recycle.bin",
               "system volume information", "_h_stage", "recovery",
               "_thumbs", "_enrichment", "_staging"}


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


_hcache: dict[str, str] = {}


def fhash(p: str) -> str | None:
    if p in _hcache:
        return _hcache[p]
    try:
        d = hashlib.blake2b(digest_size=32)
        with open(lp(p), "rb") as f:
            for b in iter(lambda: f.read(8 << 20), b""):
                d.update(b)
    except OSError:
        return None
    _hcache[p] = d.hexdigest()
    return _hcache[p]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    # A --limit run must never be mistaken for a full one. The inventory was
    # truncated once by exactly that: a test run wrote over the real output.
    out = OUT if not a.limit else OUT.replace(".csv", f".sample{a.limit}.csv")

    # ---- library: size -> [(path, dev, ino)] ------------------------------
    lib: dict[int, list[tuple[str, int, int]]] = {}
    for root in P.INVENTORY_ROOTS:
        for dp, dns, fns in os.walk(root):
            if "_Catalog" in dp:
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(lp(p))
                except OSError:
                    continue
                lib.setdefault(st.st_size, []).append((p, st.st_dev, st.st_ino))
    nlib = sum(len(v) for v in lib.values())
    print(f"library: {nlib:,} files, {len(lib):,} distinct sizes")

    # ---- enumerate D: outside the library ---------------------------------
    srcs: list[tuple[str, int]] = []
    for top in sorted(os.listdir("D:\\")):
        if top.lower() in EXCLUDE_TOP:
            continue
        tp = os.path.join("D:\\", top)
        if not os.path.isdir(tp):
            continue
        for dp, dns, fns in os.walk(tp):
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    srcs.append((p, os.path.getsize(lp(p))))
                except OSError:
                    continue
    tot_b = sum(s for _, s in srcs)
    print(f"D: outside library: {len(srcs):,} files, {tot_b/1024**3:.1f} GB")
    if a.limit:
        srcs = srcs[:a.limit]
        print(f"  SAMPLE of {len(srcs):,} -> {out}")

    # ---- classify ---------------------------------------------------------
    counts = {"RECLAIMABLE": 0, "HARDLINK": 0, "ONLY": 0, "UNREADABLE": 0}
    bytes_ = dict.fromkeys(counts, 0)
    t0 = time.time()
    done_b = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Path", "Bytes", "Status", "Survivor"])
        for i, (p, sz) in enumerate(srcs, 1):
            cands = lib.get(sz, [])
            status, survivor = "ONLY", ""
            if cands:
                try:
                    sst = os.stat(lp(p))
                except OSError:
                    sst = None
                if sst and any((c[1], c[2]) == (sst.st_dev, sst.st_ino)
                               for c in cands):
                    status = "HARDLINK"
                    survivor = next(c[0] for c in cands
                                    if (c[1], c[2]) == (sst.st_dev, sst.st_ino))
                else:
                    sh = fhash(p)
                    if sh is None:
                        status = "UNREADABLE"
                    else:
                        for cp, _, _ in cands:
                            if fhash(cp) == sh:
                                status, survivor = "RECLAIMABLE", cp
                                break
            counts[status] += 1
            bytes_[status] += sz
            w.writerow([p, sz, status, survivor])
            done_b += sz

            if i % 2000 == 0:
                el = time.time() - t0
                frac = done_b / max(tot_b, 1)
                eta = (el / max(frac, 1e-9)) - el
                print(f"  {i:,}/{len(srcs):,}  {frac*100:.1f}%  "
                      f"{done_b/1024**3:.0f} GB done  "
                      f"ETA {eta/60:.0f} min  "
                      f"reclaim {bytes_['RECLAIMABLE']/1024**3:.0f} GB / "
                      f"only {bytes_['ONLY']/1024**3:.0f} GB", flush=True)

    print(f"\nfinished in {(time.time()-t0)/60:.1f} min -> {out}")
    for k in ("RECLAIMABLE", "HARDLINK", "ONLY", "UNREADABLE"):
        print(f"  {k:<12} {counts[k]:>8,} files  {bytes_[k]/1024**3:>8.1f} GB")
    print(f"\nSPACE ACTUALLY FREED BY DELETING: "
          f"{bytes_['RECLAIMABLE']/1024**3:.1f} GB")
    print(f"  (hardlinks free 0 GB no matter how many are removed)")
    print(f"  ONLY files are NOT deletable - they need ingesting: "
          f"{counts['ONLY']:,} files, {bytes_['ONLY']/1024**3:.1f} GB")


if __name__ == "__main__":
    main()
