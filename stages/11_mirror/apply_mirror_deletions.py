r"""Make D: match H: by applying deletions made on the MIRROR back to the source.

    python apply_mirror_deletions.py                     # report
    python apply_mirror_deletions.py --apply

Krish, 2026-09-21: *"I just deleted a bunch of the stuff in H: ContentLibrary
folder that was not in the Media or ContentProduction folders... can you mimic
those changes in the D drive?"*

THIS INVERTS THE TRUST DIRECTION, WHICH IS WHY IT IS ITS OWN TOOL

Everywhere else in this repo D: is canonical and H: is the copy. Here H: is the
record of intent and D: follows. That is fine when a human deleted from H: on
purpose, and catastrophic in every other case that produces the same symptom:

  H: not mounted                      -> "delete everything"
  H: mid-sync after a restore         -> "delete everything not yet back"
  a mirror run that never finished    -> "delete what was never uploaded"

The last one is the dangerous one, because it is invisible. A file that failed
to upload looks exactly like a file the user deleted: absent from H:, present on
D:. Deleting it destroys the only copy.

SO THERE ARE THREE GUARDS, AND NONE IS OPTIONAL

  1. A FLOOR. If H: holds less than --min-share of D:'s file count the tool
     refuses outright. An unmounted or half-synced mirror cannot authorise a
     mass deletion.
  2. THE JOURNAL DECIDES, NOT THE DIFF. `h-mirror.csv` records every file this
     engine uploaded. A D: file missing from H: is only treated as "deleted by
     the user" if the journal says it WAS uploaded. If it was never uploaded,
     H: never had it, its absence means nothing, and it is KEPT and reported.
  3. AN EXCLUDE LIST. Some trees live on D: by design and were never mirrored -
     `_Catalog` holds manifest.csv, the provenance record for 124,382 files.
     H: never needed it; its absence is not a deletion.

Every removal is hashed and journalled BEFORE the unlink, so the record survives
a kill mid-run. These files have NO surviving copy - that is the point of the
operation - so the journal is the only thing that will ever say what was here.

It does NOT add anything to the no-reingest list. These files were removed, not
purged forever: blocklisting them would silently refuse them if they are ever
re-ingested from another source, which is a different decision that nobody made.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402

SEP = chr(92)
MIRROR_ROOT = "H:" + SEP + "My Drive" + SEP + "ContentLibrary"
JOURNAL = os.path.join(P.AUDIT, "MIRROR-DELETIONS-APPLIED.csv")
MIRROR_LOG = os.path.join(P.AUDIT, "h-mirror.csv")

# Trees that live on D: by design and were never mirrored. Their absence from
# H: is not evidence of anything.
EXCLUDE = ["_catalog"]

CHUNK = 8 << 20
csv.field_size_limit(1 << 30)


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def content_hash(path: str) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(lp(path), "rb", buffering=0) as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def walk_rel(root: str) -> dict:
    out = {}
    if not os.path.isdir(root):
        return out
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            out[os.path.relpath(p, root).lower()] = p
    return out


def uploaded_sources() -> set:
    out = set()
    if not os.path.exists(MIRROR_LOG):
        return out
    for r in csv.DictReader(io.open(MIRROR_LOG, encoding="utf-8", newline="")):
        if r.get("outcome") in ("written", "already-present"):
            s = (r.get("source") or "").strip().lower()
            if s:
                out.add(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirror", default=MIRROR_ROOT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-share", type=float, default=0.80,
                    help="refuse if the mirror holds less than this fraction "
                         "of the source's files")
    ap.add_argument("--reason",
                    default="deleted from the H: mirror by Krish, 2026-09-21")
    a = ap.parse_args()

    if not os.path.isdir(a.mirror):
        print("STOPPING: the mirror is not mounted: {}".format(a.mirror))
        print("  An absent mirror cannot authorise a deletion.")
        return 1

    src = walk_rel(P.ROOT)
    mir = walk_rel(a.mirror)
    print("source {} : {:,} files".format(P.ROOT, len(src)))
    print("mirror {} : {:,} files".format(a.mirror, len(mir)))

    # GUARD 1 - the floor.
    share = (len(mir) / len(src)) if src else 0.0
    print("mirror holds {:.1%} of the source's files".format(share))
    if share < a.min_share:
        print()
        print("STOPPING: the mirror holds too little to authorise deletions.")
        print("  Below --min-share {:.0%} this looks like an unmounted or "
              "half-synced mirror,".format(a.min_share))
        print("  and the two are indistinguishable from 'the user deleted "
              "everything'.")
        return 1

    missing = sorted(set(src) - set(mir))
    kept_excluded = [r for r in missing
                     if r.split(os.sep)[0] in EXCLUDE]
    candidates = [r for r in missing
                  if r.split(os.sep)[0] not in EXCLUDE]

    # GUARD 2 - the journal decides.
    up = uploaded_sources()
    deletable, never_uploaded = [], []
    for rel in candidates:
        (deletable if src[rel].lower() in up else never_uploaded).append(rel)

    print()
    print("absent from the mirror        : {:,}".format(len(missing)))
    print("  excluded tree, KEPT         : {:,}  ({})".format(
        len(kept_excluded), ", ".join(EXCLUDE)))
    print("  never uploaded, KEPT        : {:,}  <- H: never had these, so "
          "their absence means nothing".format(len(never_uploaded)))
    print("  uploaded then removed on H: : {:,}  <- these are your deletions"
          .format(len(deletable)))

    if never_uploaded:
        print()
        print("  KEPT because they were never mirrored:")
        for rel in never_uploaded[:20]:
            print("      " + src[rel][16:110])

    tot = 0
    for rel in deletable:
        try:
            tot += os.path.getsize(lp(src[rel]))
        except OSError:
            pass
    print()
    print("would delete {:,} file(s), {:.2f} GB - NO surviving copy".format(
        len(deletable), tot / (1 << 30)))

    by_top = {}
    for rel in deletable:
        k = rel.split(os.sep)[0]
        by_top[k] = by_top.get(k, 0) + 1
    for k, v in sorted(by_top.items(), key=lambda kv: -kv[1]):
        print("    {:>7,}  {}".format(v, k))

    if not a.apply:
        print()
        print("DRY RUN - nothing touched. Re-run with --apply.")
        return 0

    if not deletable:
        print("nothing to do")
        return 0

    os.makedirs(os.path.dirname(JOURNAL), exist_ok=True)
    fresh = not os.path.exists(JOURNAL)
    fh = io.open(JOURNAL, "a", encoding="utf-8", newline="")
    w = csv.writer(fh)
    if fresh:
        w.writerow(["When", "Path", "Bytes", "Hash", "Reason"])

    gone = failed = 0
    freed = 0
    try:
        for rel in deletable:
            p = src[rel]
            try:
                size = os.path.getsize(lp(p))
                digest = content_hash(p)
            except OSError as e:
                print("  cannot read, SKIPPED: {} ({})".format(p[-70:], e))
                failed += 1
                continue
            # Journal BEFORE the unlink. These have no other copy; the record
            # is the only thing that will ever say what was here.
            w.writerow([dt.datetime.now().isoformat(timespec="seconds"),
                        p, size, digest, a.reason])
            fh.flush()
            os.fsync(fh.fileno())
            try:
                os.remove(lp(p))
            except OSError as e:
                print("  FAILED to remove {}: {}".format(p[-70:], e))
                failed += 1
                continue
            gone += 1
            freed += size
            if gone % 500 == 0:
                print("  deleted {:,}  {:.2f} GB".format(
                    gone, freed / (1 << 30)), flush=True)
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    print()
    print("deleted {:,} file(s), {:.2f} GB".format(gone, freed / (1 << 30)))
    print("failed  {:,}".format(failed))
    print("journal {}".format(JOURNAL))
    print()
    print("The records now name files that no longer exist. Next:")
    print("  python stages/04_inventory/reconcile_disk.py")
    print("  python stages/08_index/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
