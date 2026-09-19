r"""Mirror the library to H:, resumably, and prove what arrived.

    python mirror_to_h.py --status
    python mirror_to_h.py --limit 40        # a measured trial
    python mirror_to_h.py                   # the full run, resumable
    python mirror_to_h.py --clear-sources   # delete consumed sources, verified

Krish, 2026-09-18: two identical libraries, the second in the cloud, with a web
app streaming from it. This is the upload half. 82,106 files, 925.4 GB, against
an account with 1,510 GB free.

WRITING INTO A DRIVE MOUNT IS NOT UPLOADING

The bytes land in a LOCAL CACHE and upload behind it. The mount will show the
file present, at the right size, while the cloud has nothing. On this project
that illusion already produced a run where 17,102 of 17,102 files "verified"
against a cache holding the bytes just written - 140.62 GB, proven by nothing.

So three rules, each of which cost somebody something:

  1. NEVER verify by reading the destination back through the mount. The hash
     that matters is of THE BYTES THAT WERE WRITTEN, computed as they were
     written (migrate_library.copy_hashing's insight).
  2. The DriveFS `operations` queue is the witness for departure, and
     `cloud_has` for arrival. An unreadable queue is NEVER treated as zero.
  3. THROTTLE. H:'s cache volume has ~131 GB free against a 925 GB library. A
     writer faster than the uploader fills the cache and takes the machine with
     it. So: write a batch, wait for the queue to drain and the cache to
     recover, continue.

WHY IT IS DRIVEN FROM THE INDEX

`library.db` already holds path, hash and bytes for every file, hashed at
ingest. Walking 925 GB to rediscover that costs an hour and learns nothing new -
and `os.walk` silently yields nothing on an unusable path, which is how a
"complete" pass over an empty set reports success.

THE JOURNAL IS APPEND-ONLY

`move_audio_to_h.py` opens its log with mode "w". For a 30-minute music move
that is survivable; for a multi-day 925 GB upload that gets killed - and this
machine kills long jobs - it destroys the record of everything already
uploaded on every restart. Here every line is appended and fsynced, and a
restart reads it back and skips what it names.

MD5 AS WELL AS BLAKE2B

Our hashes are blake2b-256. Drive exposes only a server-side `md5Checksum`, and
that is the sole evidence the cloud can offer about a file's content. Computing
both in the single read means the eventual verification needs no second pass
over 925 GB.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import time

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401

import paths as P                                                 # noqa: E402

DEST_ROOT = r"H:\My Drive\ContentLibrary"
JOURNAL = os.path.join(P.AUDIT, "h-mirror.csv")
FIELDS = ["when", "source", "dest", "bytes", "blake2b", "md5", "outcome"]
CHUNK = 8 << 20
LONGPATH = "\\\\?\\"

# Throttles.
#
# THE CACHE FLOOR IS THE GATE. THE QUEUE IS INFORMATIONAL.
#
# QUEUE_CEILING was 400, a number I invented - learning 54 exactly, a threshold
# nobody measured. DriveFS's `operations` table sits naturally around 380-450
# while uploading steadily, so the mirror spent hours oscillating between
# "waiting: queue 423 (ceiling 400)" and "queue 398 - resuming", making almost
# no progress while Drive was perfectly willing to accept more. Measured
# 2026-09-18: the true depth drifted 408 -> 384 -> 382 -> 380 while the writer
# sat idle believing it was backed up.
#
# What actually protects this machine is disk: DriveFS stages through
# %LOCALAPPDATA%\Google\DriveFS on C:, so running out of cache is the failure
# that hurts. The queue ceiling is now high enough to catch a genuine runaway
# (DriveFS falling badly behind) and nothing tighter.
QUEUE_CEILING = 3000         # a real backlog, not the normal working level

# THE FLOOR AND THE FILE SIZE HAVE TO FIT IN THE VOLUME TOGETHER.
#
# This was 40.0, and it deadlocked the mirror three files from the end.
#
# The arithmetic nobody did: steady-state free space on the constrained volume
# is ~45.7 GB, and MAX_FILE_GB is 20. A floor of 40 leaves 5.7 GB usable, so the
# largest permitted file could NEVER be written - not when the queue drained, not
# ever. The run sat at 3 files outstanding repeating
# "waiting for room for 7.6 GB: 45.7 GB free, floor 40" until the supervisor
# called it stalled, killed it, and the task restarted it to do the same thing.
# A throttle that can never open is a deadlock wearing the costume of patience.
#
# The measurement that settles what the floor is actually for: the DriveFS cache
# directory under %LOCALAPPDATA%\Google\DriveFS holds 1.0 GB. Not tens. The
# floor was guarding against a volume filling that was never filling - learning
# 54 exactly, a threshold nobody measured, and I had just rewritten
# QUEUE_CEILING for that same reason without checking its neighbour.
#
# So the rule, and it is checkable rather than felt:
#
#     CACHE_FLOOR_GB + MAX_FILE_GB <= the volume's steady-state free space
#
# 25 + 20 = 45, against 45.7 GB measured. Writing the largest permitted file
# leaves 25 GB on C:, which is comfortable for Windows, and DriveFS evicts as
# the upload completes.
CACHE_FLOOR_GB = 25.0        # the gate: stop if C:/H: headroom drops below this
WAIT_SECONDS = 60
MAX_WAIT_ROUNDS = 240        # 4 hours of waiting before giving up a batch


# The drive the destination lives on. Set from --dest in main(); the default is
# the drive of DEST_ROOT. lp() refuses to prefix anything on it - see below.
MOUNT_DRIVE = os.path.splitdrive(DEST_ROOT)[0].lower()


def lp(p: str) -> str:
    r"""The \\?\ prefix - EXCEPT on the Drive mount, where it does not resolve.

    DriveFS is a filter driver, not a real volume, and it relies on the path
    normalisation that \\?\ exists to skip. On the mount, that prefix makes
    os.path.exists answer False for a file that is plainly there, and opening an
    existing file for write answer [Errno 22] Invalid argument. The purge hit
    the same wall from the other side: \\?\H:\... gave WinError 123 where the
    plain path worked.

    Two files were reported "copy failed: [Errno 22] Invalid argument" on every
    single run because of it. Their destinations were already present at exactly
    the right size, so the correct outcome was "already-present" - but that
    check is `os.path.exists(lp(dst))`, which could not see them, and the
    overwrite it fell through to could not happen either. Mirroring 82,055 NEW
    files hid the bug completely: CREATING a file that does not exist yet
    survives the bad prefix, so only the handful of re-writes ever failed.

    Dropping the prefix on the mount costs nothing measurable here: the longest
    destination path in the library is 238 characters and not one reaches 255.
    Source paths on D: still get it - that is where the long paths actually are.
    """
    if p.startswith(LONGPATH):
        return p
    if os.path.splitdrive(p)[0].lower() == MOUNT_DRIVE:
        return p
    return LONGPATH + p


def _accounts():
    for acct in glob.glob(os.path.join(P.DRIVEFS, "1*")):
        db = os.path.join(acct, "metadata_sqlite_db")
        if os.path.exists(db):
            yield acct, db


def _snapshot(db: str, tag: str):
    r"""Copy the metadata db AND its write-ahead log before reading it.

    Copying only `metadata_sqlite_db` reads the last COMMITTED state and misses
    everything still in `metadata_sqlite_db-wal`, which on 2026-09-18 was 63 MB.
    Measured three times, seconds apart: 408 vs 384, 382 vs 382, 382 vs 380. So
    the number was stale by up to 26 operations and could sit frozen while the
    real value moved - which is how the throttle came to wait on a figure that
    looked dead.
    """
    tmp = os.path.join(tempfile.gettempdir(), "dfs_mirror_{}.db".format(tag))
    shutil.copy2(db, tmp)
    for suffix in ("-wal", "-shm"):
        side = db + suffix
        if os.path.exists(side):
            try:
                shutil.copy2(side, tmp + suffix)
            except OSError:
                pass
    con = sqlite3.connect(tmp)
    con.text_factory = bytes
    return con


def queue_depth(marker: str = "ContentLibrary") -> int | None:
    r"""Pending operations for the account that owns the DESTINATION.

    `move_audio_to_h.queue_depth` picks the account with the most
    `local_title LIKE '%.mp3'` - it identifies "the account that owns the files"
    by counting mp3s, which is right for a music move and points at the wrong
    account for a photograph library. Two accounts are mounted here.

    So the marker is a parameter: the account holding the most items whose
    title matches it is the one being uploaded to. Falls back to the account
    with the most items if the marker matches nothing yet, which is the case on
    the very first run.

    Returns None when nothing can be read. None is never treated as zero.
    """
    best = None
    for acct, db in _accounts():
        try:
            con = _snapshot(db, os.path.basename(acct)[:8])
            owned = con.execute(
                "SELECT COUNT(*) FROM items WHERE local_title LIKE ?",
                ("%" + marker + "%",)).fetchone()[0]
            total = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            pending = con.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
            con.close()
        except Exception:                                # noqa: BLE001
            continue
        rank = (owned, total)
        if best is None or rank > best[0]:
            best = (rank, pending)
    return best[1] if best else None


def cache_free_gb() -> float | None:
    r"""The REAL constraint, which is C: and not H:.

    H: reports a 475.6 GB volume with some amount free, and that number is the
    local cache's, not the account's (learning 17). Worse for a writer: DriveFS
    stages everything through `%LOCALAPPDATA%\Google\DriveFS`, which lives on
    C:. Measured 2026-09-18: that folder held 107.0 GB - 90.8 GB of it for the
    H: account - while C: had 81.0 GB free. So writing 824 GB "to H:" writes it
    through a cache on the system disk.

    Taking the smaller of the two is the only honest headroom, and it is the
    number that stops a mirror from filling somebody's boot drive.
    """
    vals = []
    for d in ("H:\\", "C:\\"):
        try:
            vals.append(shutil.disk_usage(d).free / (1 << 30))
        except OSError:
            pass
    return min(vals) if vals else None


def load_done() -> dict:
    """source -> journalled row, for everything already written."""
    done = {}
    if not os.path.exists(JOURNAL):
        return done
    with io.open(JOURNAL, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("outcome") or "") in ("written", "already-present"):
                done[(r.get("source") or "").lower()] = r
    return done


def append(rows: list) -> None:
    fresh = not os.path.exists(JOURNAL)
    with io.open(JOURNAL, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(FIELDS)
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())


#: A single file larger than this is not a photograph or a home video, and a
#: cloud mirror should not carry it. `1000002434.jpg` is 101 GB of NULL BYTES -
#: sampled at five offsets including its last sixteen, and not sparse - a failed
#: copy that has been sitting in NoDate since September. A `--limit 6 --largest`
#: trial picked it first because it IS the largest file, wrote 80.2 GB of zeros
#: to the mount, and took H:'s cache from 131 GB to 81 GB before being stopped.
#: Anything over this ceiling is deferred and named, never silently skipped.
MAX_FILE_GB = 20.0


def planned(db_path: str) -> list:
    """(source, bytes, hash) for every library file, from the INDEX."""
    db = sqlite3.connect("file:{}?mode=ro".format(
        db_path.replace("\\", "/")), uri=True)
    try:
        rows = db.execute(
            "select path, bytes, hash from files order by bytes").fetchall()
    finally:
        db.close()
    out, oversized = [], []
    for p, b, h in rows:
        if not p:
            continue
        b = b or 0
        if b / (1 << 30) > MAX_FILE_GB:
            oversized.append((p, b))
            continue
        out.append((p, b, h or ""))
    if oversized:
        print("EXCLUDED as implausibly large (over {:.0f} GB each):".format(
            MAX_FILE_GB))
        for p, b in sorted(oversized, key=lambda t: -t[1]):
            print("  {:>8.1f} GB  {}".format(b / (1 << 30), p))
        print("  These need a human decision, not a cloud copy. Nothing is")
        print("  hidden: they are listed on every run until they are dealt with.")
        print()
    return out


def dest_for(src: str) -> str:
    rel = os.path.relpath(src, P.ROOT)
    return os.path.join(DEST_ROOT, rel)


def copy_hashing(src: str, dst: str):
    """Copy once; return (blake2b, md5, bytes) of what was written."""
    b = hashlib.blake2b(digest_size=32)
    m = hashlib.md5()
    n = 0
    with open(lp(src), "rb", buffering=0) as fi, \
            open(lp(dst), "wb", buffering=0) as fo:
        while True:
            chunk = fi.read(CHUNK)
            if not chunk:
                break
            b.update(chunk)
            m.update(chunk)
            fo.write(chunk)
            n += len(chunk)
    try:
        shutil.copystat(lp(src), lp(dst))
    except OSError:
        pass
    return b.hexdigest(), m.hexdigest(), n


def wait_for_room(say=print) -> bool:
    """Let DriveFS catch up. False means give up rather than fill the cache."""
    for i in range(MAX_WAIT_ROUNDS):
        q = queue_depth()
        free = cache_free_gb()
        if free is None:
            say("  cannot read the cache headroom - refusing to write blind")
            return False
        # An unreadable queue is NOT a reason to stop any more.
        #
        # It used to be: `if q is None: return False`. On 2026-09-18 that ended
        # a 781-minute run with 497 GB unsent, because the queue read failed
        # once. The queue is now informational - the cache floor is what makes
        # writing unsafe - so an unreadable queue is reported and the run
        # continues on the constraint that actually matters.
        if q is None:
            say("  DriveFS queue unreadable; continuing on cache headroom "
                "({:.1f} GB free, floor {:.0f})".format(free, CACHE_FLOOR_GB))
            return free >= CACHE_FLOOR_GB
        if q <= QUEUE_CEILING and free >= CACHE_FLOOR_GB:
            if i:
                say("  queue {:,}, cache {:.1f} GB free - resuming".format(q, free))
            return True
        if i == 0 or i % 5 == 0:
            say("  waiting: queue {:,} (ceiling {:,}), cache {:.1f} GB free "
                "(floor {:.0f})".format(q, QUEUE_CEILING, free, CACHE_FLOOR_GB))
        time.sleep(WAIT_SECONDS)
    say("  waited {} minutes and DriveFS never caught up".format(
        MAX_WAIT_ROUNDS * WAIT_SECONDS // 60))
    return False


def wait_for_headroom(size: int, say=print) -> bool:
    r"""Wait until THIS file fits above the cache floor. False = it never did.

    `wait_for_room` answers a different question - "is the cache healthy enough
    to keep writing?" - and a healthy cache with 8 GB of headroom still cannot
    take an 18.6 GB file. So the size has to be part of the condition.

    Why this exists: the per-file check used to journal DEFERRED and move on,
    which is why the last 27 files of an 824 GB mirror could never be sent. All
    27 were over 2.7 GB, the cache only frees as uploads COMPLETE, so every run
    deferred all of them within seconds and exited, the task restarted, and it
    deferred them again. The counter sat at 27 for hours while the machine
    looked busy.

    It also broke the chain's preflight, which probes with `--limit 1`. The
    index is size-ordered ascending, so the probe picks the SMALLEST outstanding
    file - by then 2.74 GB - which deferred as well. The probe wrote nothing,
    the preflight refused to commit to the run, and the mirror had stopped
    itself for good with 136 GB outstanding.

    Measured while finding this: the client uploads at 8.73 MB/s sustained, and
    H:'s free space rose 42.4 -> 48.0 GB across three minutes as completed
    uploads were evicted. The headroom returns on its own. The only thing
    missing was the patience to wait for it.
    """
    need = size / (1 << 30)
    for i in range(MAX_WAIT_ROUNDS):
        free = cache_free_gb()
        if free is None:
            say("  cannot read the cache headroom - refusing to write blind")
            return False
        if need <= free - CACHE_FLOOR_GB:
            if i:
                say("  {:.1f} GB now fits ({:.1f} GB free, floor {:.0f})".format(
                    need, free, CACHE_FLOOR_GB))
            return True
        if i == 0 or i % 5 == 0:
            q = queue_depth()
            say("  waiting for room for {:.1f} GB: {:.1f} GB free, floor {:.0f}"
                ", queue {}".format(need, free, CACHE_FLOOR_GB,
                                    "{:,}".format(q) if q is not None else "?"))
        time.sleep(WAIT_SECONDS)
    say("  waited {} minutes and {:.1f} GB never fit above the floor".format(
        MAX_WAIT_ROUNDS * WAIT_SECONDS // 60, need))
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--dest", default=DEST_ROOT)
    ap.add_argument("--limit", type=int, default=0,
                    help="upload this many files and stop - for a measured trial")
    ap.add_argument("--largest", action="store_true",
                    help="with --limit, take the BIGGEST files rather than the "
                         "smallest. The index is ordered by size ascending, so a "
                         "plain --limit 40 trialled the 40 emptiest files in the "
                         "library - 1,157 bytes in total, several of them zero. "
                         "It proved the plumbing and measured nothing, because "
                         "887 of the 925 GB is video. Any throughput claim has "
                         "to come from the large end.")
    ap.add_argument("--band", default="",
                    help="MIN-MAX in MB, e.g. 200-800: trial the size band the "
                         "library actually consists of. --largest picks the "
                         "extreme tail, which on this library meant six files "
                         "averaging 25 GB and a cache emergency; the bulk of "
                         "the 887 GB of video is a few hundred MB a file, and "
                         "that is what a throughput figure should come from.")
    ap.add_argument("--batch", type=int, default=25,
                    help="check the queue and the cache every N files")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    files = planned(a.db)
    done = load_done()
    todo = [t for t in files if t[0].lower() not in done]
    total_b = sum(b for _, b, _ in files)
    done_b = sum(int(r.get("bytes") or 0) for r in done.values())

    print("library      : {:,} files   {:.1f} GB".format(
        len(files), total_b / (1 << 30)))
    print("journalled   : {:,} files   {:.1f} GB".format(
        len(done), done_b / (1 << 30)))
    print("still to send: {:,} files   {:.1f} GB".format(
        len(todo), (total_b - done_b) / (1 << 30)))
    q = queue_depth()
    free = cache_free_gb()
    print("DriveFS queue: {}".format("UNREADABLE" if q is None else "{:,}".format(q)))
    print("H: cache free: {}".format(
        "UNREADABLE" if free is None else "{:.1f} GB".format(free)))

    if a.status:
        return 0
    if not todo:
        print("\nnothing left to send.")
        return 0

    # --band, ACTUALLY IMPLEMENTED.
    #
    # It was declared in argparse and never read, so `--limit 40 --band 50-300`
    # silently fell through to "smallest first" and re-sent the same 40 empty
    # files, printing "sample too small to project a rate" - the flag's own
    # name reading as coverage it did not have. Fourth time tonight that a
    # flag was added without the behaviour behind it (learning 57's last line).
    how = "smallest first"
    if a.band:
        try:
            lo_mb, hi_mb = (float(x) for x in a.band.split("-", 1))
        except ValueError:
            sys.exit("--band wants MIN-MAX in MB, e.g. 50-300")
        lo, hi = int(lo_mb * (1 << 20)), int(hi_mb * (1 << 20))
        before = len(todo)
        todo = [t for t in todo if lo <= t[1] <= hi]
        how = "{:.0f}-{:.0f} MB band".format(lo_mb, hi_mb)
        print("\nband {}: {:,} of {:,} outstanding files qualify".format(
            a.band, len(todo), before))
        if not todo:
            print("nothing in that band is outstanding.")
            return 0

    if a.limit:
        if a.largest:
            todo = sorted(todo, key=lambda t: -t[1])[:a.limit]
            how = "largest first"
        else:
            todo = todo[:a.limit]
        gb = sum(b for _, b, _ in todo) / (1 << 30)
        print("TRIAL: {} file(s), {:.2f} GB ({})".format(len(todo), gb, how))
        if gb < 0.5:
            print("  WARNING: this sample is too small to measure anything.")
            print("  Use --band 50-300 for a throughput figure.")

    # Before the first lp() call on a destination path: --dest may put the
    # mirror on a different drive than DEST_ROOT, and lp() has to know which
    # drive is the mount so it can leave those paths unprefixed.
    global MOUNT_DRIVE
    MOUNT_DRIVE = os.path.splitdrive(os.path.abspath(a.dest))[0].lower()

    os.makedirs(lp(a.dest), exist_ok=True)
    t0 = time.time()
    sent = skipped = failed = 0
    sent_b = 0
    throttled = False
    pending: list = []

    for i, (src, size, want) in enumerate(todo, 1):
        # CHECK BEFORE EVERY LARGE FILE, not only every `batch` files.
        #
        # The throttle originally fired every 25 files. A `--limit 6 --largest`
        # trial then picked six files averaging 25 GB - 150.5 GB in total,
        # including a 101 GB one - and never reached a checkpoint at all: it
        # would have written straight through the 40 GB cache floor and taken
        # the machine with it. A batch count is the wrong unit for a throttle
        # that exists to protect a byte budget.
        big = size >= (2 << 30)
        if (i % a.batch == 1 and i > 1) or (big and i > 1):
            if pending:
                append(pending)
                pending = []
            if not wait_for_room():
                print("\nSTOPPING on throttle. Everything sent so far is "
                      "journalled; re-run to continue.")
                throttled = True
                break

        # A single file bigger than the cache headroom can never be safe to
        # write here, whatever the queue says.
        free_gb = cache_free_gb()
        if free_gb is not None and size / (1 << 30) > (free_gb - CACHE_FLOOR_GB):
            # WAIT for the room. Do not skip the file.
            #
            # Skipping is what stranded the last 27 files of the library: all of
            # them over 2.7 GB, a cache that only frees as uploads complete, so
            # every run deferred all 27 in seconds and exited for the task to
            # restart and defer them again. See wait_for_headroom.
            if not wait_for_headroom(size):
                now = dt.datetime.now().isoformat(timespec="seconds")
                pending.append([now, src, dest_for(src), size, "", "",
                                "DEFERRED: {:.1f} GB and the cache never freed "
                                "(was {:.1f} GB free)".format(
                                    size / (1 << 30), free_gb)])
                skipped += 1
                # A throttle stop must exit non-zero so the task restarts.
                throttled = True
                break
            free_gb = cache_free_gb()

        dst = dest_for(src)
        now = dt.datetime.now().isoformat(timespec="seconds")
        try:
            os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
        except OSError as e:
            failed += 1
            pending.append([now, src, dst, size, "", "", "mkdir failed: {}".format(e)])
            continue

        # Already there at the right size from an earlier, unjournalled run?
        # Recorded as such, and NOT as proof the cloud has it - that is what
        # the queue and cloud_has are for.
        try:
            if os.path.exists(lp(dst)) and os.path.getsize(lp(dst)) == size:
                skipped += 1
                pending.append([now, src, dst, size, "", "", "already-present"])
                continue
        except OSError:
            pass

        try:
            bl, md, n = copy_hashing(src, dst)
        except OSError as e:
            failed += 1
            pending.append([now, src, dst, size, "", "", "copy failed: {}".format(e)])
            continue

        # VERIFIED BY THE BYTES THAT WERE WRITTEN, not by reading the mount.
        if n != size:
            failed += 1
            pending.append([now, src, dst, size, bl, md,
                            "SHORT WRITE {} of {}".format(n, size)])
            continue
        if want and bl != want:
            failed += 1
            pending.append([now, src, dst, size, bl, md,
                            "HASH MISMATCH, index said {}".format(want[:16])])
            continue

        sent += 1
        sent_b += n
        pending.append([now, src, dst, size, bl, md, "written"])

        if len(pending) >= 25:
            append(pending)
            pending = []
        if sent and sent % 100 == 0:
            el = max(time.time() - t0, 1)
            rate = sent_b / el / (1 << 20)
            left = (sum(b for _, b, _ in todo) - sent_b) / (1 << 30)
            print("  {:,}/{:,}  {:.1f} GB sent  {:.1f} MB/s  ~{:.1f} GB left"
                  .format(i, len(todo), sent_b / (1 << 30), rate, left),
                  flush=True)

    if pending:
        append(pending)

    el = max(time.time() - t0, 1)
    print()
    print("written {:,}, already there {:,}, failed {:,}".format(
        sent, skipped, failed))
    print("bytes   {:.2f} GB in {:.0f}s".format(sent_b / (1 << 30), el))
    # DO NOT EXTRAPOLATE FROM A TRIVIAL SAMPLE.
    #
    # The 40-file trial wrote under 10 MB in 1 second and this printed
    # "LOCAL WRITE RATE: 0.0 MB/s ... the remaining 925.3 GB takes 344,653.5 h".
    # Arithmetically true, completely meaningless, and destined for a log read
    # at 2am by somebody deciding whether the job is healthy. A projection from
    # a sample too small to carry one is worse than no projection.
    if sent_b >= (1 << 30) and el >= 60:
        rate = sent_b / el / (1 << 20)
        remaining = (total_b - done_b - sent_b) / (1 << 20)
        print("LOCAL WRITE RATE: {:.1f} MB/s".format(rate))
        print("  the remaining {:.1f} GB reaches the CACHE in ~{:.1f} h".format(
            remaining / 1024, remaining / rate / 3600))
        print("  that is NOT the upload time. The bytes upload asynchronously;")
        print("  the honest figure is the DriveFS queue draining.")
    elif sent_b:
        print("sample too small to project a rate from "
              "({:.1f} MB in {:.0f}s) - no ETA claimed".format(
                  sent_b / (1 << 20), el))
    q = queue_depth()
    print("DriveFS queue now: {}".format(
        "UNREADABLE" if q is None else "{:,}".format(q)))
    print("journal: {}".format(JOURNAL))

    # A THROTTLE STOP MUST EXIT NON-ZERO, OR THE NIGHT ENDS SILENTLY.
    #
    # On 2026-09-18 the run stopped after 781 minutes because queue_depth()
    # returned None and the throttle refused to write blind - the guard working
    # exactly as intended. But it exited 0, the Task Scheduler read that as
    # success, the task went Ready, and 1,639 files carrying 497 GB - all of the
    # large video - sat unsent with nothing to restart it. chain_mirror_h.ps1's
    # Postcondition fails on purpose so the task restarts; a clean exit walks
    # straight past it.
    #
    # Unfinished is not success. RestartCount then does its job and the next run
    # resumes from the journal.
    if throttled:
        print()
        print("exiting non-zero: the run is UNFINISHED. The supervisor restarts")
        print("on a non-zero exit and the next run resumes from the journal.")
        return 2
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
