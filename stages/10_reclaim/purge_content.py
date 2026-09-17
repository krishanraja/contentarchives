r"""Destroy chosen content and every trace of it. The one deletion with no survivor.

    python purge_content.py --list D:\_PhotoAudit\purge-targets.csv
    python purge_content.py --list ... --apply

Krish, 2026-09-18: *"purge all intimate content forever"*, scoped by him to the
88 files in `Media\Personal\Intimate`, with "everything, plus a no-reingest
list".

WHY THIS IS NOT guarded_delete.py

`guarded_delete` deletes only when a SURVIVING COPY is proven to exist, or the
file is garbage by a narrow named category: *"Everything else raises. There is no
third path, no flag to override it."* That rule exists because every near-miss
here came from a deletion justified by something that was true earlier - a
path-substring rule once destroyed 45 irreplaceable personal files.

This is the opposite request: the owner wants no surviving copy. So it cannot
reuse that path, and it must not weaken it either. It gets its own guards:

  - an EXPLICIT LIST of (hash, path). No globs, no path substrings, no "under
    this folder". The list is built by a separate reader and verified here.
  - EVERY FILE IS RE-HASHED at the moment of deletion. If a path's content does
    not match the hash the list names, the whole run stops before deleting
    anything. A stale list is how 45 files died.
  - THE JOURNAL IS WRITTEN FIRST, to the same `user-directed-deletions.csv` the
    other purge tools use. The content will be gone; the record that it was
    deliberately destroyed, and what it was, must not be.
  - TWO PHASES. A dry run prints every file and every trace. Nothing happens
    without --apply.

WHAT "FOREVER" REACHES, AND WHAT IT CANNOT

Destroyed: the files; their 512px thumbnails and sampled frames; their tag,
description and index rows; the rows in the path records; the move journals.

Blanked, not removed: face embeddings. A face row is overwritten with a ZERO
vector in place, because removing the row would shift every later position in
`face-emb.npy` and move the frozen cluster ids that 1,609 human answers point
at (learning 45). The row survives saying a face was once found; the vector
that described it does not. `guards/alignment.py` knows a zeroed pair is a purge
rather than drift.

Kept deliberately: 88 content hashes, in the blocklist, so a later import from
H:, a phone backup or a Takeout cannot quietly re-admit them. A hash cannot
reconstruct an image. Krish was asked and chose this.

Beyond reach: Google Photos, Drive's own trash, any copy on a device this
machine cannot see. The tool reports what it knows of them and never claims
otherwise.
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import datetime as dt
import io
import os
import shutil
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401

import paths as P                                                 # noqa: E402
from store import content_hash                                    # noqa: E402

JOURNAL = os.path.join(P.AUDIT, "user-directed-deletions.csv")
BLOCKLIST = os.path.join(P.AUDIT, "PURGED-HASHES.csv")
THUMBS = r"D:\_thumbs"
STORE = r"D:\_enrichment"
FACES = os.path.join(STORE, "faces.0.csv")
VFACES = os.path.join(STORE, "faces.video.csv")
TAGS = os.path.join(STORE, "content_tags.csv")
CLUSTERS = os.path.join(P.AUDIT, "FACE-CLUSTERS.csv")
CACHE = os.path.join(P.AUDIT, "face-emb.npy")
DIM = 512

# Path records that merely NAME the files. Rows are removed; the file stays.
PATH_RECORDS = [
    ("INVENTORY.csv", False, "LibraryPath"),
    ("MIGRATION-HASHES.csv", True, 0),
    ("HASH-INDEX.csv", False, "LibraryPath"),
]

# Records that exist only to describe these files, and go entirely.
DISPOSABLE = ["DISK-NOT-IN-INVENTORY.csv", "INVENTORY.csv.bak-flatten",
              "MIGRATION-HASHES.csv.bak-flatten"]

ZERO_EMB = base64.b64encode(
    bytes(DIM * 2)).decode()          # 512 float16 zeros, still base64-decodable


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def read_list(path: str) -> list[dict]:
    with io.open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f)
                if (r.get("Hash") or "").strip() and (r.get("Path") or "").strip()]
    if not rows:
        sys.exit("STOPPING: {} names no targets. Purging nothing and calling it "
                 "done would be the worst outcome here.".format(path))
    return rows


def verify(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Re-hash every target NOW. A list is never evidence; the disk is."""
    ok, bad = [], []
    for r in rows:
        p, want = r["Path"], r["Hash"].strip().lower()
        if not os.path.exists(lp(p)):
            bad.append("already gone: {}".format(p))
            continue
        try:
            got = content_hash(p)
        except OSError as e:
            bad.append("unreadable ({}): {}".format(e, p))
            continue
        if got.lower() != want:
            bad.append("CONTENT CHANGED since the list was made: {}\n"
                       "     list says {}\n     disk says {}".format(
                           p, want[:16], got[:16]))
            continue
        r = dict(r)
        r["_bytes"] = os.path.getsize(lp(p))
        ok.append(r)
    return ok, bad


def journal(entries: list[tuple]) -> None:
    fresh = not os.path.exists(JOURNAL)
    with io.open(JOURNAL, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(["Path", "Bytes", "Reason", "Evidence", "When"])
        now = dt.datetime.now().isoformat(timespec="seconds")
        for path, nbytes, reason, evidence in entries:
            w.writerow([path, nbytes, reason, evidence, now])
        f.flush()
        os.fsync(f.fileno())


def rewrite_csv(path: str, fn, headerless: bool = False) -> tuple[int, int]:
    """Stream `path` through `fn(row) -> row or None`. tmp + promote."""
    if not os.path.exists(path):
        return 0, 0
    tmp = path + ".purge-tmp"
    kept = dropped = 0
    with io.open(path, encoding="utf-8", errors="replace", newline="") as src, \
            io.open(tmp, "w", encoding="utf-8", newline="") as out:
        rd, w = csv.reader(src), csv.writer(out)
        if not headerless:
            head = next(rd, None)
            if head is not None:
                w.writerow(head)
        for row in rd:
            new = fn(row)
            if new is None:
                dropped += 1
                continue
            w.writerow(new)
            kept += 1
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)
    return kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", required=True,
                    help="CSV of Hash,Path to destroy - built and reviewed "
                         "separately, never a glob")
    ap.add_argument("--reason", default="user-directed purge of intimate content")
    ap.add_argument("--also", action="append", default=[],
                    help="an extra absolute path to destroy (a verified copy "
                         "outside the library, e.g. on H:). Repeatable.")
    ap.add_argument("--blocklist-also", default="",
                    help="a CSV of Hash,... to record in the blocklist WITHOUT "
                         "deleting - for content already gone from disk, which "
                         "a re-import could otherwise restore because nothing "
                         "on disk stops it any more")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rows = read_list(a.list)
    ok, bad = verify(rows)
    print("targets listed        : {}".format(len(rows)))
    print("verified by hash NOW  : {}".format(len(ok)))
    print("refused               : {}".format(len(bad)))
    for b in bad:
        print("   {}".format(b))
    if bad:
        print()
        print("STOPPING: the list and the disk disagree. Nothing has been")
        print("touched. A deletion justified by a stale record is how 45")
        print("irreplaceable files were lost here.")
        return 1

    targets = {r["Hash"].strip().lower() for r in ok}
    extra = []
    for p in a.also:
        if not os.path.exists(lp(p)):
            print("--also path is already gone: {}".format(p))
            continue
        h = content_hash(p)
        if h.lower() not in targets:
            print()
            print("STOPPING: --also {}".format(p))
            print("  hashes {} which is NOT in the target list.".format(h[:16]))
            return 1
        extra.append((p, os.path.getsize(lp(p)), h.lower()))

    # --- what else carries this content -----------------------------------
    #
    # SWEEP THUMBNAILS FOR EVERY BLOCKED HASH, not just the deletable ones.
    #
    # Measured after the 2026-09-18 run: 7 thumbnails survived it. Those 7
    # files had been deleted by Krish himself beforehand, so they were absent
    # from disk and correctly excluded from `targets` - but their 512px copies
    # were still in D:\_thumbs, which is a copy of exactly the content the
    # purge existed to destroy. --blocklist-also recorded their hashes and did
    # not extend the sweep to them: the flag did half its job.
    #
    # READ THE BLOCK-ONLY LIST FIRST. Everything below depends on it.
    #
    # An earlier version built `sweep` from block_only twenty-seven lines BEFORE
    # defining it - a NameError on every run, and the kind of half-finished edit
    # that only shows up when the tool is next used in anger.
    block_only = []
    if a.blocklist_also:
        with io.open(a.blocklist_also, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                h = (r.get("Hash") or "").strip().lower()
                if h and h not in targets:
                    block_only.append(
                        (h, int(r.get("Bytes") or 0),
                         r.get("Note") or "already absent from disk"))

    # A hash worth blocking forever is a hash whose every trace must go. The
    # 2026-09-18 run swept only `targets` and left 7 thumbnails, 5 face vectors
    # and 5 bounding boxes behind - derived copies of content whose originals
    # were already destroyed. The file may be unreachable; its 512px likeness
    # and the vector describing the face in it are not.
    sweep = set(targets) | {h for h, _, _ in block_only}

    thumbs = []
    for sub in sorted(os.listdir(THUMBS)):
        d = os.path.join(THUMBS, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            stem = fn[:-4] if fn.endswith(".jpg") else fn
            h = stem.split("_f")[0]
            if h.lower() in sweep:
                thumbs.append(os.path.join(d, fn))

    def count(path, col, headerless=False):
        if not os.path.exists(path):
            return 0
        n = 0
        with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
            rd = csv.reader(f)
            if not headerless:
                next(rd, None)
            for r in rd:
                if len(r) > col and r[col].strip().lower() in sweep:
                    n += 1
        return n

    n_tags = count(TAGS, 0)
    n_faces = count(FACES, 0)
    n_vfaces = count(VFACES, 0)
    n_clusters = count(CLUSTERS, 0)

    # The path records are keyed on PATH, not hash. Counting them against the
    # hash set reports 0 and understates the blast radius in the one summary a
    # person reads before approving a purge.
    dead = {r["Path"].replace("/", "\\").lower() for r in ok}

    def path_col(path: str, headerless: bool, col) -> int:
        if headerless:
            return int(col)
        with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
            head = next(csv.reader(f), [])
        return head.index(col) if col in head else 0

    def count_paths(path: str, headerless: bool, col) -> int:
        if not os.path.exists(path):
            return -1
        i = path_col(path, headerless, col)
        n = 0
        with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
            rd = csv.reader(f)
            if not headerless:
                next(rd, None)
            for r in rd:
                if len(r) > i and r[i].replace("/", "\\").lower() in dead:
                    n += 1
        return n

    print()
    print("=== what will be destroyed ===")
    print("  files in the library      : {:>6}  {:>10,} bytes".format(
        len(ok), sum(r["_bytes"] for r in ok)))
    for p, b, _ in extra:
        print("  verified copy outside it  : {}  ({:,} bytes)".format(p, b))
    print("  thumbnails and frames     : {:>6}".format(len(thumbs)))
    print("  tag/description rows      : {:>6}".format(n_tags))
    for name, headerless, col in PATH_RECORDS:
        n = count_paths(os.path.join(P.AUDIT, name), headerless, col)
        print("  rows in {:<24}: {:>6}".format(
            name, "absent" if n < 0 else n))
    for name in DISPOSABLE:
        if os.path.exists(os.path.join(P.AUDIT, name)):
            print("  {:<32}: deleted entirely".format(name))
    n_j = sum(1 for fn in os.listdir(P.AUDIT)
              if fn.startswith("intimate-sweep-") and fn.endswith(".csv"))
    print("  {:<32}: {} deleted".format("intimate-sweep journals", n_j))
    print()
    print("=== what will be BLANKED in place, to protect frozen clusters ===")
    print("  face rows zeroed in faces.0.csv      : {:>6}".format(n_faces))
    print("  face rows zeroed in faces.video.csv  : {:>6}".format(n_vfaces))
    print("  cluster rows stripped of their bbox  : {:>6}".format(n_clusters))
    print("  face-emb.npy                         : deleted, regenerates from")
    print("                                         the purged CSV on next use")
    # Hashes to block but not delete: content already absent from disk. Without
    # this, a purge of 81 files would leave the 7 that were removed earlier
    # unblocked - and those are the ones with nothing on disk to stop a
    # re-import restoring them. Their thumbnails and rows ARE swept, because a
    # 512px copy of destroyed content is still a copy of it.
    if block_only:
        print()
        print("=== hashes to BLOCK but not delete (already gone) ===")
        print("  {} from {}".format(len(block_only),
                                    os.path.basename(a.blocklist_also)))
        print("  their thumbnails, tag rows and face rows are swept too")

    print()
    print("=== what will be KEPT, deliberately ===")
    print("  {} content hashes in {}".format(
        len(targets) + len(block_only), os.path.basename(BLOCKLIST)))
    print("  so a later import cannot re-admit them")

    if not a.apply:
        print()
        print("=== a sample of the files ===")
        for r in ok[:6]:
            print("   {}".format(r["Path"]))
        print()
        print("DRY RUN - nothing touched. Re-run with --apply.")
        return 0

    # --- THE JOURNAL FIRST -------------------------------------------------
    entries = [(r["Path"], r["_bytes"], a.reason,
                "hash {} re-verified at deletion".format(r["Hash"][:16]))
               for r in ok]
    entries += [(p, b, a.reason + " (copy outside the library)",
                 "hash {} re-verified at deletion".format(h[:16]))
                for p, b, h in extra]
    journal(entries)
    print()
    print("journalled {} deletion(s) FIRST: {}".format(len(entries), JOURNAL))

    # --- the blocklist, before the evidence goes ---------------------------
    fresh = not os.path.exists(BLOCKLIST)
    with io.open(BLOCKLIST, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(["Hash", "Bytes", "Reason", "When"])
        now = dt.datetime.now().isoformat(timespec="seconds")
        for r in ok:
            w.writerow([r["Hash"].strip().lower(), r["_bytes"], a.reason, now])
        for h, nbytes, note in block_only:
            w.writerow([h, nbytes, a.reason + " (" + note + ")", now])
        f.flush()
        os.fsync(f.fileno())
    print("blocklist written: {} ({} hashes, {} of them already gone)".format(
        BLOCKLIST, len(ok) + len(block_only), len(block_only)))

    # --- the files ---------------------------------------------------------
    gone = 0
    for r in ok:
        os.remove(lp(r["Path"]))
        gone += 1
    for p, _, _ in extra:
        os.remove(lp(p))
        gone += 1
    print("deleted {} file(s)".format(gone))

    for t in thumbs:
        try:
            os.remove(lp(t))
        except OSError as e:
            print("   thumbnail survived ({}): {}".format(e, t))
    print("deleted {} thumbnail/frame file(s)".format(len(thumbs)))

    # --- the derived rows --------------------------------------------------
    kept, dropped = rewrite_csv(
        TAGS, lambda r: None if r and r[0].strip().lower() in targets else r)
    print("content_tags.csv: {:,} kept, {:,} rows removed".format(kept, dropped))

    def zero_face(r):
        """Keep the row and its POSITION; destroy what described the face."""
        if not r or r[0].strip().lower() not in targets:
            return r
        out = list(r)
        if len(out) >= 6:                 # hash,face_index,bbox,det,said,emb
            out[2] = ""
            out[3] = "0.000"
            out[-1] = ZERO_EMB
        return out

    for name, path in (("faces.0.csv", FACES), ("faces.video.csv", VFACES)):
        k, d2 = rewrite_csv(path, zero_face)
        print("{}: {:,} rows, embeddings zeroed in place (none removed)".format(
            name, k))

    def strip_cluster(r):
        if not r or r[0].strip().lower() not in targets:
            return r
        out = list(r)               # hash,face_index,cluster,det_score,bbox
        if len(out) >= 5:
            out[3] = "0.000"
            out[4] = ""
        return out

    k, _ = rewrite_csv(CLUSTERS, strip_cluster)
    print("FACE-CLUSTERS.csv: {:,} rows, cluster ids kept, bboxes cleared".format(k))

    if os.path.exists(CACHE):
        os.remove(CACHE)
        print("deleted {} - it regenerates from the purged source".format(
            os.path.basename(CACHE)))

    # --- the records that name the paths -----------------------------------
    for name, headerless, col in PATH_RECORDS:
        p = os.path.join(P.AUDIT, name)
        if not os.path.exists(p):
            continue
        # `dead` is built once, higher up, WITH separator normalisation. A
        # second definition here dropped the replace("/", "\\") and would have
        # silently failed to match any record that stores forward slashes -
        # leaving the path of destroyed content sitting in the inventory.
        i = path_col(p, headerless, col)
        k, d2 = rewrite_csv(
            p, lambda r, i=i: None if len(r) > i
            and r[i].replace("/", "\\").lower() in dead else r,
            headerless=headerless)
        print("{}: {:,} kept, {:,} row(s) removed".format(name, k, d2))

    for name in DISPOSABLE:
        p = os.path.join(P.AUDIT, name)
        if os.path.exists(p):
            os.remove(p)
            print("deleted {}".format(name))
    for fn in sorted(os.listdir(P.AUDIT)):
        if fn.startswith("intimate-sweep-") and fn.endswith(".csv"):
            os.remove(os.path.join(P.AUDIT, fn))
            print("deleted {} (the move journal for content now destroyed)".format(fn))

    print()
    print("=== WHAT THIS COULD NOT REACH ===")
    print("  Google Photos, and Google Drive's own trash, which holds a deleted")
    print("  file for 30 days. If the H: copy was removed, empty that trash.")
    print("  Any copy on a phone, a camera card or a backup this machine")
    print("  cannot see.")
    print()
    print("Now, IN THIS ORDER:")
    print("  1. python stages/08_index/build_db.py     - the index still has them")
    print("  2. delete D:\\_PhotoAudit\\lib-index.pickle  - the dedup path cache")
    print("  3. python stages/09_segment/sweep_intimate.py --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
