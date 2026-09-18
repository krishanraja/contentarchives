r"""The uploader had no test at all. It has moved 655 GB.

    python tests\test_mirror_to_h.py

WHY THIS EXISTS

`mirror_to_h.py` is the tool that puts the second copy of the library in the
cloud, and until now nothing in `tests/` named it. Every bug it has had this
week was found by watching it run - 81 GB of null bytes written to Drive before
a size ceiling existed, a throttle waiting on a threshold nobody measured, a
writer exiting 0 on a partial upload - which is the most expensive way to find
any of them.

WHAT IS PINNED, AND WHY EACH ONE COST SOMETHING

  1. lp() DOES NOT PREFIX A PATH ON THE DRIVE MOUNT. DriveFS is a filter
     driver, not a volume, and it needs the path normalisation that \\?\ skips.
     With the prefix, os.path.exists answers False for a file that is plainly
     there and opening an existing file for write answers [Errno 22]. Two files
     failed on every run for exactly this: their destinations were already
     present at the right size, the already-present check could not see them,
     and the overwrite it fell through to could not happen. 82,055 NEW files
     hid it, because creating a file that does not exist survives the prefix.

     Honest limit: a normal volume ACCEPTS \\?\, so no test on C: can reproduce
     DriveFS's refusal. What is pinned here is the DECISION - mount paths go
     unprefixed - not the mount's response to being given one.

  2. lp() STILL PREFIXES SOURCE PATHS. That is where the long paths are; the
     library has source paths past 260 characters and dropping the prefix
     everywhere would fail them instead.

  3. MOUNT_DRIVE FOLLOWS --dest. lp() decides by drive letter, so a mirror
     pointed somewhere else has to move the exemption with it.

  4. copy_hashing RETURNS THE BYTES IT WROTE, and both digests match a
     hashlib pass over the source. The verification standard here is the bytes
     WRITTEN, never a read-back through the mount: a cache read-back is what
     once "verified" 140.62 GB the cloud did not have (learning 25).

  5. THE JOURNAL'S FIELD NAMES DO NOT MOVE. The chain's -Verify block re-derives
     from `source` and compares `blake2b`, and Remaining counts `outcome`. A
     renamed column would not fail loudly - it would make the verify sample
     nothing and the count read zero.
"""

import hashlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "stages", "11_mirror"))
sys.path.insert(0, os.path.join(REPO, "stages", "_shared"))

import mirror_to_h as M                                          # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(
        name, "OK" if ok else "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


LONG = "\\\\?\\"

print()
print("1. lp() leaves a path on the Drive mount alone")
M.MOUNT_DRIVE = "h:"
dst = r"H:\My Drive\ContentLibrary\Media\Personal\2021\2021-03\IMG.jpg"
check("a mount path is returned unchanged", M.lp(dst), dst)
check("no prefix was added", M.lp(dst).startswith(LONG), False)
# Lower-case drive letters are the same drive.
check("the drive letter's case does not matter",
      M.lp(dst.replace("H:", "h:")), dst.replace("H:", "h:"))

print()
print("2. lp() still prefixes a source path on another drive")
src = r"D:\ContentLibrary\Media\Personal\2021\2021-03\IMG.jpg"
check("a source path is prefixed", M.lp(src), LONG + src)
check("and prefixing is idempotent", M.lp(M.lp(src)), LONG + src)

print()
print("3. MOUNT_DRIVE follows the destination, not a hardcoded H:")
try:
    M.MOUNT_DRIVE = "e:"
    check("H: is prefixed once the mount moves to E:", M.lp(dst), LONG + dst)
    check("E: is now the exempt drive",
          M.lp(r"E:\ContentLibrary\x.jpg"), r"E:\ContentLibrary\x.jpg")
finally:
    M.MOUNT_DRIVE = os.path.splitdrive(M.DEST_ROOT)[0].lower()
check("restored from DEST_ROOT", M.MOUNT_DRIVE, "h:")

print()
print("4. dest_for() mirrors the library's relative path under the dest root")
rel = os.path.join("Media", "Personal", "2021", "2021-03", "IMG.jpg")
want = os.path.join(M.DEST_ROOT, rel)
check("relative structure is preserved",
      M.dest_for(os.path.join(M.P.ROOT, rel)), want)

print()
print("5. copy_hashing reports the bytes it WROTE, with both digests")
tmp = tempfile.mkdtemp(prefix="mirror-test-")
try:
    # Not compressible, not a repeated byte: a run of zeros would make a short
    # write and a correct one hash differently only by length.
    payload = os.urandom(3 * 1024 * 1024 + 17)
    s = os.path.join(tmp, "source.bin")
    d = os.path.join(tmp, "out", "dest.bin")
    os.makedirs(os.path.dirname(d))
    with io.open(s, "wb") as fh:
        fh.write(payload)

    # The temp tree is on a normal volume, so exempt it the way the mount is
    # exempt - the point is to exercise the real call path, not \\?\ on C:.
    M.MOUNT_DRIVE = os.path.splitdrive(os.path.abspath(tmp))[0].lower()
    bl, md, n = M.copy_hashing(s, d)

    check("byte count is what the source holds", n, len(payload))
    check("blake2b matches a fresh pass over the source",
          bl, hashlib.blake2b(payload, digest_size=32).hexdigest())
    check("md5 matches too (Drive compares md5Checksum)",
          md, hashlib.md5(payload).hexdigest())
    check("the destination really holds those bytes",
          io.open(d, "rb").read() == payload, True)
finally:
    M.MOUNT_DRIVE = os.path.splitdrive(M.DEST_ROOT)[0].lower()
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("6. the journal's field names are what the chain parses")
for col in ("source", "dest", "bytes", "blake2b", "md5", "outcome"):
    check("journal still has a '{}' column".format(col), col in M.FIELDS, True)
check("outcome is the last column", M.FIELDS[-1], "outcome")

print()
print("7. the throttle constants are measured numbers, not invented ones")
# QUEUE_CEILING was 400 - a threshold nobody measured, while DriveFS sits at
# 380-450 while uploading steadily, so the mirror oscillated for hours. The
# cache floor is the real gate; these pin the relationship, not the values.
check("the cache floor is the gate and is positive", M.CACHE_FLOOR_GB > 0, True)
check("a single file cannot exceed the cache floor by design",
      M.MAX_FILE_GB > M.CACHE_FLOOR_GB, False)
check("the queue ceiling is above DriveFS's steady state (~450)",
      M.QUEUE_CEILING > 450, True)

print()
print("8. wait_for_headroom answers about THIS file's size, not the cache's mood")
# The bug it exists to prevent: the per-file check journalled DEFERRED and moved
# on, so the last 27 files of the library - every one over 2.7 GB, against a
# cache that only frees as uploads complete - were deferred anew on every run
# and never sent. It also deferred the chain's one-file probe, which made the
# preflight refuse to start the run at all.
_real_free = M.cache_free_gb
_real_queue = M.queue_depth
_real_rounds = M.MAX_WAIT_ROUNDS
_real_wait = M.WAIT_SECONDS
_said = []
try:
    # BOUND THE WAIT FIRST. The real values are 240 rounds with a sleep
    # between each, so the failing case below would sit here for hours - a test
    # that hangs is a test nobody runs, and this file exists because nobody was
    # running one.
    M.MAX_WAIT_ROUNDS = 2
    M.WAIT_SECONDS = 0
    M.queue_depth = lambda *a, **k: 123   # no 225 MB snapshot inside a test

    # Plenty of room: returns at once, says nothing.
    M.cache_free_gb = lambda: M.CACHE_FLOOR_GB + 50.0
    check("a file that fits returns true immediately",
          M.wait_for_headroom(int(2.7 * (1 << 30)), say=_said.append), True)
    check("and it does not narrate a wait it never made", _said, [])

    # Exactly at the floor is NOT room: the floor is a floor, not a target.
    M.cache_free_gb = lambda: M.CACHE_FLOOR_GB + 2.0
    check("a file larger than the headroom does not pass",
          M.wait_for_headroom(int(3.0 * (1 << 30)), say=_said.append) is True,
          False)

    # An unreadable headroom must refuse rather than write blind.
    _said2 = []
    M.cache_free_gb = lambda: None
    check("an unreadable cache refuses rather than guessing",
          M.wait_for_headroom(int(1 * (1 << 30)), say=_said2.append), False)
    check("and it says why", any("refusing to write blind" in s for s in _said2),
          True)
finally:
    M.cache_free_gb = _real_free
    M.queue_depth = _real_queue
    M.MAX_WAIT_ROUNDS = _real_rounds
    M.WAIT_SECONDS = _real_wait

print()
if FAILURES:
    print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("all checks passed")
sys.exit(0)
