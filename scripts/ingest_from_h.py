r"""Stream H: into the library in batches, routed, deduplicated, without filling D:.

WHY BATCHES

The staged copy and the library entry co-exist until the batch is cleared, so a
single pull would need headroom for the largest folder. Batching keeps peak
usage to one batch, and a batch that fails costs one batch.

    pull batch -> route -> ingest each destination -> delete batch

WHY ROUTING, ADDED AFTER from-machine-b

The first folder ingested put 1,252 files into the media chronology, of which
987 were QA screenshots of the user's own apps, path-flattened Downloads and
business videos. Nothing was lost, but the chronology is the thing this project
exists to build, and it is not a dumping ground. Every file now gets a
destination decided by route_h before it is placed:

    chronology  -> Media/<year>/<year-month>     a photograph or video
    production  -> ContentProduction/<folder>    produced, not remembered
    archive     -> Archive/FromH/<folder>        documents, admin, audio

Routing is reversible and journalled with the signal that caused it. Deletion
is not reversible, so nothing here deletes anything from H:.

WHAT IS NEVER PULLED

.lrv and .lrf - GoPro and DJI low-resolution proxies generated beside their own
originals, 27.6 GB of the 371 GB on H:. Plus .thm stubs, Thumbs.db and
zero-byte files. Ingesting a proxy puts a 1.4 MB stand-in next to the 90 MB
original it stands in for.

WHY SINGLE-STREAM

Measured on this mount: one stream 10.5 MB/s, four streams 8.1 MB/s aggregate.
Parallelism is 23% WORSE - the account is throttled and concurrency only adds
contention. The hours this takes are a floor, not a tuning failure.

WHY IT COPIES BEFORE HASHING

Never hash off the Drive mount: it hangs with zero bytes read rather than
failing (learning 15), and reading a placeholder hydrates it, filling C:
(learning 5). Copy local, then hash.

    python ingest_from_h.py --all                 # dry run, every folder
    python ingest_from_h.py --all --apply
    python ingest_from_h.py --folder from-gopro-2024 --apply
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P                                                # noqa: E402
from route_h import route, CHRONOLOGY, PRODUCTION_D, ARCHIVE     # noqa: E402

H_ROOT = r"H:\My Drive\_photo-consolidation"
# The stage must live on the library's own volume: ingest_tree HARDLINKS out of
# it when source and library share a drive, which is what makes a batch cost its
# bytes once instead of twice. Derive it, so moving the library to a bigger disk
# is the one edit in paths.py it is supposed to be.
LIB_VOL = os.path.splitdrive(P.ROOT)[0] + os.sep
STAGE = os.path.join(LIB_VOL, "_h_stage")
# Where a file that defeated the batch copier is pulled by hand. It is
# journalled with this root rather than the stage, so the resume set has to
# recognise both - otherwise the next run helpfully re-fetches the one file
# that was hardest to get.
RESCUE = os.path.join(LIB_VOL, "_h_rescue")
LOG = os.path.join(P.AUDIT, "h-ingest.csv")
ROUTE_LOG = os.path.join(P.AUDIT, "H-ROUTING.csv")

# Derived files generated beside their own originals. .lrprev is Lightroom's
# preview cache - 1,888 of them were found on D: - and is no more a photograph
# than a GoPro .lrv proxy is.
NEVER = {".lrv", ".lrf", ".thm", ".db", ".ini", ".lrprev", ".picasa.ini"}

# This project's own tooling, not the user's content. Named explicitly rather
# than pattern-matched, so adding a folder to H: cannot silently skip it.
SKIP_FOLDERS = {"_audit-trail", "in", "out"}

# D: is a data volume; C: is the system disk. 40 GB leaves room for one 20 GB
# batch plus slack. Measured: ingest_tree HARDLINKS from the stage because both
# live on D:, so a batch costs its own bytes once, not twice.
MIN_FREE_GB = 40.0
BATCH_GB = 20.0

# Memory-dense camera folders first. If anything goes wrong at hour six, the
# irreplaceable material is already in.
PRIORITY = ["from-dji-2026 (cannes and wedding)", "from-gopro-2024",
            "user - Phone Backup - Jun to Sep 2025",
            "content production & podcasts (may be duplicates)",
            "from-personal-google-drive", "from-boogles", "from-wd6400"]

DEST_ROOT = {
    CHRONOLOGY:   None,                       # ingest_tree's own chronology
    PRODUCTION_D: os.path.join(P.PRODUCTION, "FromH"),
    ARCHIVE:      os.path.join(P.ARCHIVE, "FromH"),
}


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


# shutil.copy2 asks Windows for one enormous transfer, and the Drive mount
# cannot service it: DJI_20260623150233_0097_D.MP4, 3.95 GB, failed with
# [WinError 1450] Insufficient system resources on two separate runs, a week
# apart. It is deterministic, not transient - which means that file would never
# have entered the library, and the only trace was one printed line in a log
# nobody reads to the end. Copying it in 8 MB pieces asks for something the
# mount can actually do.
CHUNK = 8 * 1024 * 1024


def copy_chunked(src: str, dst: str) -> None:
    with open(src, "rb", buffering=0) as fi, open(dst, "wb", buffering=0) as fo:
        while True:
            b = fi.read(CHUNK)
            if not b:
                break
            fo.write(b)
    shutil.copystat(src, dst)


def free_gb(d: str = "") -> float:
    """Headroom on the volume the library is actually on.

    This read "D:\\" while every other path came from paths.py. The floor that
    stops a batch filling the disk would then have been measuring a drive the
    library had moved off - reporting healthy space on the wrong volume, which
    is the failure this project keeps paying for."""
    return shutil.disk_usage(d or LIB_VOL).free / 1024 ** 3


BUCKETS = ("chronology", "production", "archive")


def handled_from_stage() -> set:
    r"""Every H: file already through the pipeline, as (relpath.lower(), size).

    do_folder rebuilds its batch list from a full folder scan on every run, so a
    re-run after an interruption re-pulls everything already ingested. At the
    measured 10.5 MB/s that is not a wasted CPU cycle, it is hours: the DJI and
    GoPro folders alone are 144 GB, and the session that died mid-batch would
    have paid 3.8 h to re-fetch bytes already on D:.

    The durable record is the autopilot journals, not the per-batch INGEST
    reports: the journals are append-only, and the reports were being written to
    one filename per folder, so batches 1-3 of DJI are gone from them.

    Keyed on name AND size. Name alone would skip a different file that happens
    to share a name; size alone is meaningless. A false skip here is a file that
    never enters the library and is never reported missing, which is the worst
    outcome this project has, so the key is deliberately strict and the count is
    printed for every folder.
    """
    handled = set()

    def key(origin: str, size: int) -> None:
        low = origin.lower()
        for root in (STAGE, RESCUE):
            if low.startswith(root.lower() + os.sep):
                break
        else:
            return
        rel = origin[len(root) + 1:]
        head = rel.split(os.sep)[0].lower()
        if head in BUCKETS:                     # stage layout is STAGE\<bucket>\<rel>
            rel = rel[len(head) + 1:]
        if rel:
            handled.add((rel.lower(), size))

    added = os.path.join(P.AUDIT, "autopilot-added.csv")
    if os.path.exists(added):
        with open(added, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                dest, origin = row[0], row[1]
                try:                            # the size is the library copy's:
                    sz = os.path.getsize(dest)  # same bytes, and still on disk
                except OSError:
                    continue                    # gone from the library: re-pull it
                key(origin, sz)

    # ingest_tree calls autopilot.record() for NEW files only. A file it rejects
    # as a duplicate, or drops under the 20 KB floor, is written to its own
    # per-batch report and nowhere else - so the resume set never learned about
    # it and every resumed run pulled it again. Measured on the phone backup:
    # of 1,571 files copied in batches 1-2, 964 were journalled and 607 were
    # not. Batch 1 was 343 files of which 342 were duplicates: 20.0 GB fetched
    # across a 10.5 MB/s link, discarded, and queued to be fetched again.
    #
    # The reports are durable now that each batch writes its own file, so read
    # them. A duplicate is only skipped if the twin it was matched against is
    # STILL on disk - if the survivor was deleted, the file must come back.
    for rep in os.listdir(P.AUDIT):
        if not (rep.startswith("INGEST-") and rep.endswith(".csv")):
            continue
        try:
            with open(os.path.join(P.AUDIT, rep), newline="",
                      encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    out = (row.get("Outcome") or "").strip()
                    srcp = row.get("Source") or ""
                    if out == "duplicate":
                        dest = row.get("Destination") or ""
                        try:
                            key(srcp, os.path.getsize(dest))
                        except OSError:
                            pass                 # survivor gone: pull it again
                    elif out == "skipped-tiny":
                        note = (row.get("Note") or "").split()
                        if note and note[0].isdigit():
                            key(srcp, int(note[0]))
        except OSError:
            continue

    dups = os.path.join(P.AUDIT, "autopilot-duplicates.csv")
    if os.path.exists(dups):
        with open(dups, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.reader(f):
                if len(row) < 3:
                    continue
                try:
                    key(row[0], int(row[2]))
                except ValueError:
                    continue
    return handled


def scan(src_root: str) -> tuple[list, int, int]:
    files, proxy, empty = [], 0, 0
    for dp, dns, fns in os.walk(src_root):
        for fn in fns:
            p = os.path.join(dp, fn)
            ext = os.path.splitext(fn)[1].lower()
            try:
                sz = os.path.getsize(p)       # metadata only, no hydration
            except OSError:
                continue
            if ext in NEVER:
                proxy += 1
                continue
            if sz == 0:
                empty += 1
                continue
            files.append((p, sz))
    return files, proxy, empty


def do_folder(folder: str, apply: bool, rw: csv.writer | None,
              handled: set | None = None) -> None:
    src_root = os.path.join(H_ROOT, folder)
    if not os.path.isdir(src_root):
        print(f"  no such folder: {folder}")
        return

    files, proxy, empty = scan(src_root)
    seen = len(files)
    seen_b = sum(s for _, s in files)
    if handled:
        keep, done_n, done_b = [], 0, 0
        for p, sz in files:
            rel = os.path.relpath(p, src_root)
            if (rel.lower(), sz) in handled:
                done_n += 1
                done_b += sz
            else:
                keep.append((p, sz))
        files = keep
        if done_n:
            print(f"    already ingested, not re-pulled: {done_n:,} files, "
                  f"{done_b/1024**3:.1f} GB "
                  f"({done_b/1024**2/10.5/3600:.1f} h of transfer saved)")
    total = sum(s for _, s in files)
    if not files:
        print("")
        print(f"=== {folder}")
        print(f"    nothing left to pull ({seen:,} files, "
              f"{seen_b/1024**3:.1f} GB all accounted for)")
        return

    routed: dict[str, list] = {CHRONOLOGY: [], PRODUCTION_D: [], ARCHIVE: []}
    for p, sz in files:
        rel = os.path.relpath(p, src_root)
        d, why = route(rel)
        routed[d].append((p, sz, rel))
        if rw:
            rw.writerow([folder, rel, d, why, sz])

    print(f"\n=== {folder}")
    print(f"    {len(files):,} files, {total/1024**3:.1f} GB   "
          f"(proxies skipped {proxy:,}, zero-byte {empty:,})")
    for d in (CHRONOLOGY, PRODUCTION_D, ARCHIVE):
        n = len(routed[d])
        b = sum(x[1] for x in routed[d])
        if n:
            print(f"      {d:<11} {n:>6,}  {b/1024**3:>7.1f} GB")

    batches, cur, cur_b = [], [], 0
    for item in sorted(files, key=lambda x: x[0]):
        if cur and cur_b + item[1] > BATCH_GB * 1024 ** 3:
            batches.append(cur)
            cur, cur_b = [], 0
        cur.append(item)
        cur_b += item[1]
    if cur:
        batches.append(cur)
    print(f"    batches of ~{BATCH_GB:g} GB: {len(batches)}   "
          f"pull at 10.5 MB/s: {total/1024**2/10.5/3600:.1f} h")

    if not apply:
        return

    lookup = {p: (d, rel) for d in routed for p, sz, rel in routed[d]}

    new_j = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as jf:
        w = csv.writer(jf)
        if new_j:
            w.writerow(["Folder", "Batch", "Files", "Bytes", "FreeGBAfter"])

        for i, batch in enumerate(batches, 1):
            if free_gb() < MIN_FREE_GB:
                print(f"\n  HALT: D: down to {free_gb():.1f} GB "
                      f"(floor {MIN_FREE_GB}). Batches already ingested are "
                      f"kept; re-run to continue.")
                return
            bb = sum(s for _, s in batch)
            print(f"\n  batch {i}/{len(batches)}: {len(batch):,} files, "
                  f"{bb/1024**3:.1f} GB  (D: {free_gb():.0f} GB free)",
                  flush=True)

            copied = 0
            for p, sz in batch:
                d, rel = lookup[p]
                dst = os.path.join(STAGE, d, rel)
                os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
                try:
                    try:
                        shutil.copy2(lp(p), lp(dst))
                    except OSError as e:
                        # One retry in pieces before giving up on the file.
                        print(f"      {type(e).__name__} {getattr(e, 'winerror', '')}"
                              f" on {rel[:40]} - retrying in 8 MB chunks",
                              flush=True)
                        try:
                            os.remove(lp(dst))
                        except OSError:
                            pass
                        copy_chunked(lp(p), lp(dst))
                    if os.path.getsize(lp(dst)) != sz:
                        print(f"      SIZE MISMATCH after copy: {rel[:60]}")
                        os.remove(lp(dst))
                        continue
                    copied += 1
                except OSError as e:
                    # A file that cannot be copied is not a log line, it is a
                    # file that will never enter the library. Name it in a file
                    # that survives the run.
                    print(f"      copy failed {rel[:50]}: {e}")
                    with open(os.path.join(P.AUDIT, "H-COPY-FAILURES.csv"), "a",
                              newline="", encoding="utf-8") as ff:
                        csv.writer(ff).writerow([folder, rel, sz, str(e)])
            print(f"    copied {copied:,}/{len(batch):,}", flush=True)

            safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in folder)
            for d in (CHRONOLOGY, PRODUCTION_D, ARCHIVE):
                sub = os.path.join(STAGE, d)
                if not os.path.isdir(sub) or not any(os.scandir(sub)):
                    continue
                # The label names the report file, and ingest_tree rewrites it.
                # Reusing one label across batches meant batch 4 overwrote
                # batches 1-3: the DJI folder's report showed 33 of 170 files.
                # The placement record (autopilot-added.csv) is append-only and
                # kept everything, but a per-run report that silently loses
                # earlier runs is worse than no report.
                cmd = [sys.executable, "-u",
                       os.path.join(P.SCRIPTS, "ingest_tree.py"),
                       "--source", sub,
                       "--label", f"h-{safe}-{d}-b{i:02d}", "--apply"]
                if DEST_ROOT[d]:
                    cmd += ["--dest-root", os.path.join(DEST_ROOT[d], folder),
                            "--any-ext"]
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   errors="replace")
                print(f"    [{d}]")
                for line in (r.stdout or "").splitlines()[-6:]:
                    print("      " + line)
                if r.returncode != 0:
                    print(f"      ingest_tree exited {r.returncode}")
                    for line in (r.stderr or "").splitlines()[-5:]:
                        print("      ! " + line)

            w.writerow([folder, i, copied, bb, f"{free_gb():.1f}"])
            jf.flush()
            os.fsync(jf.fileno())

            # Clearing the stage is not optional bookkeeping - it is what keeps
            # peak usage at one batch. rmtree with ignore_errors=True hides its
            # own failure, and 24 silently uncleaned batches fill the disk. So:
            # no error suppression, and the result is checked.
            try:
                shutil.rmtree(STAGE)
            except OSError as e:
                print(f"    stage cleanup failed: {e}")
            if os.path.isdir(STAGE):
                left = sum(os.path.getsize(os.path.join(dp, f))
                           for dp, dn, fs in os.walk(STAGE) for f in fs)
                print(f"    HALT: stage still holds {left/1024**3:.1f} GB after "
                      f"cleanup. Continuing would fill D:. Clear "
                      f"{STAGE} and re-run.")
                return

    print(f"\n  {folder}: {len(batches)} batches done. D: {free_gb():.1f} GB free")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if a.all:
        present = {d for d in os.listdir(H_ROOT)
                   if os.path.isdir(os.path.join(H_ROOT, d))}
        folders = [f for f in PRIORITY if f in present]
        # anything on H: that PRIORITY does not name must be reported, never
        # silently skipped - the plan missed 6 of 11 folders once already
        unlisted = present - set(PRIORITY) - SKIP_FOLDERS - {"from-machine-b"}
        if unlisted:
            print(f"NOT IN PRIORITY LIST, will be done last: {sorted(unlisted)}")
            folders += sorted(unlisted)
    elif a.folder:
        folders = [a.folder]
    else:
        sys.exit("give --folder NAME or --all")

    print(f"folders to process ({len(folders)}):")
    for f in folders:
        print(f"  {f}")

    # append, not truncate: "w" erased the routing record of every file
    # already placed each time the run was resumed.
    fresh = not os.path.exists(ROUTE_LOG)
    rf = open(ROUTE_LOG, "a", newline="", encoding="utf-8") if a.apply else None
    rw = None
    if rf:
        rw = csv.writer(rf)
        if fresh:
            rw.writerow(["Folder", "RelPath", "Destination", "Signal", "Bytes"])
    handled = handled_from_stage()
    print("")
    print(f"already through the pipeline from H:: {len(handled):,} files")
    try:
        for f in folders:
            do_folder(f, a.apply, rw, handled)
    finally:
        if rf:
            rf.close()

    if not a.apply:
        print("\nDRY RUN - nothing copied. Re-run with --apply.")


if __name__ == "__main__":
    main()
