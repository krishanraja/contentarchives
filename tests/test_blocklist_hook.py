r"""The no-reingest list existed for a day and nothing read it.

    python tests\test_blocklist_hook.py

WHY THIS EXISTS

Krish, 2026-09-18: *"purge all intimate content forever"*. 88 hashes were
destroyed and written to `PURGED-HASHES.csv`, and until this hook was added
**no code anywhere read that file**. The blocklist was inert. Ten old communal
phones, photographs of family albums and VHS conversions are all still to be
ingested over the coming weeks, and any one of them carrying a copy would have
re-admitted it silently - filed, thumbnailed, described and indexed like
anything else.

"Forever" is a property of the INGEST, not of the delete. A purge that only
unlinks files is a purge with a time limit.

WHAT IS PINNED

  1. A BLOCKED FILE IS REFUSED BY CONTENT. Not by name, not by path, not by
     date - the copy on a phone shares none of those with the original
     (learning 1, learning 57).
  2. A FILE WHOSE SIZE IS NOT BLOCKED IS NEVER HASHED. 88 files must not make
     every future ingest read every byte of every candidate. The size gates the
     hash - learning 7 used in the other direction: size rules out, only a hash
     rules in. Proved by making `full_hash` raise: if the gate leaks, the test
     fails loudly rather than slowly.
  3. SAME SIZE, DIFFERENT CONTENT IS ADMITTED (learnings 22 and 36).
  4. EVERY REFUSAL IS JOURNALLED, with the hash and the source. A file that
     silently vanishes mid-ingest is indistinguishable from a bug.
  5. AN UNREADABLE FILE WHOSE SIZE MATCHES IS REFUSED. It cannot be cleared, and
     this is the one case where being wrong is irreversible.
  6. A BLOCKLIST ROW WITHOUT A 64-HEX HASH IS IGNORED AND COUNTED, not trusted.
     A broken writer put a SIZE in the Hash column once (learning 60).
  7. AN ABSENT BLOCKLIST BLOCKS NOTHING, and says so. "No file" and "no
     entries" must not look like a working blocklist that matches nothing.
"""

import csv
import hashlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "stages", "02_ingest"))
sys.path.insert(0, os.path.join(REPO, "stages", "_shared"))

import autopilot as A                                            # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<66} {}".format(
        name, "OK" if ok else "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def write(path, data: bytes):
    with io.open(path, "wb") as fh:
        fh.write(data)
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def reset(rows):
    """Point autopilot at a fixture blocklist and clear its cache."""
    A._BLOCKED = None
    with io.open(A.BLOCKLIST, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Hash", "Bytes", "Reason", "When"])
        for r in rows:
            w.writerow(r)
    if os.path.exists(A.BLOCKLOG):
        os.remove(A.BLOCKLOG)


tmp = tempfile.mkdtemp(prefix="blocklist-test-")
_real_block, _real_log, _real_cache = A.BLOCKLIST, A.BLOCKLOG, A._BLOCKED
_real_hash = A.full_hash
_said = []
_real_logfn = A.log
try:
    A.BLOCKLIST = os.path.join(tmp, "PURGED-HASHES.csv")
    A.BLOCKLOG = os.path.join(tmp, "autopilot-blocked.csv")
    A.log = _said.append          # keep the real log file out of a test run

    purged = os.path.join(tmp, "purged.jpg")
    body = b"the content that was destroyed" * 40
    h_purged = write(purged, body)
    size = os.path.getsize(purged)

    innocent = os.path.join(tmp, "innocent.jpg")
    h_innocent = write(innocent, b"a different family photograph" * 40)

    # Same SIZE as the purged file, different content.
    twin = os.path.join(tmp, "twin.jpg")
    h_twin = write(twin, b"X" * len(body))

    print()
    print("1. a blocked file is refused by content, under any name")
    reset([[h_purged, size, "user-directed purge", "2026-09-17T21:50:58"]])
    idx = A.blocked_index()
    check("the list loaded, keyed by size", sorted(idx.keys()), [size])
    check("with the hash in it", h_purged in idx[size], True)
    # A copy under a completely different name, as a phone would carry it.
    renamed = os.path.join(tmp, "IMG_9931_from_a_phone.jpg")
    write(renamed, body)
    A._HASH_CACHE.clear()
    check("the renamed copy is refused", A.is_blocked(renamed, size), True)

    print()
    print("2. same size, different content is admitted")
    A._HASH_CACHE.clear()
    check("the twin is not blocked", A.is_blocked(twin, size), False)
    check("(and it really is the same size)",
          os.path.getsize(twin), size)
    check("(and really a different hash)", h_twin == h_purged, False)

    print()
    print("3. a file whose SIZE is not blocked is never hashed")
    def explode(*a, **k):
        raise AssertionError("full_hash was called for an unblocked size")
    A.full_hash = explode
    try:
        A._HASH_CACHE.clear()
        got = A.is_blocked(innocent, os.path.getsize(innocent))
        check("admitted without reading a byte", got, False)
    except AssertionError as e:
        check("admitted without reading a byte", str(e), "not called")
    finally:
        A.full_hash = _real_hash

    print()
    print("4. every refusal is journalled with its hash")
    rows = list(csv.DictReader(io.open(A.BLOCKLOG, encoding="utf-8",
                                       newline="")))
    check("one row for the one refusal", len(rows), 1)
    check("it names the file", os.path.basename(rows[0]["source"]),
          "IMG_9931_from_a_phone.jpg")
    check("and carries the real hash", rows[0]["hash"], h_purged)
    check("and the byte count", rows[0]["bytes"], str(size))

    print()
    print("5. an unreadable file whose size matches is refused, not admitted")
    A.full_hash = lambda *a, **k: None
    try:
        check("refused because it cannot be cleared",
              A.is_blocked(os.path.join(tmp, "not-there.jpg"), size), True)
    finally:
        A.full_hash = _real_hash

    print()
    print("6. a row whose Hash column is not a hash is ignored and counted")
    _said[:] = []
    reset([[h_purged, size, "real", "now"],
           ["73208", "IMG-20211121-WA0000.jpg", "the learning 60 bug", "now"],
           ["", "", "", ""]])
    idx = A.blocked_index()
    check("only the real hash loaded", sum(len(v) for v in idx.values()), 1)
    check("and the bad row was reported",
          any("no 64-hex hash" in s for s in _said), True)
    A._HASH_CACHE.clear()
    check("the real hash still blocks", A.is_blocked(purged, size), True)

    print()
    print("7. a blocked entry with no size forces hashing of every candidate")
    reset([[h_purged, "", "size unknown", "now"]])
    idx = A.blocked_index()
    check("it is filed under -1", -1 in idx, True)
    A._HASH_CACHE.clear()
    check("a candidate of any size is still checked",
          A.is_blocked(purged, 999999), True)
    A._HASH_CACHE.clear()
    check("and an innocent one of that size is admitted",
          A.is_blocked(innocent, 999999), False)

    print()
    print("8. an absent blocklist blocks nothing, and says so")
    A._BLOCKED = None
    os.remove(A.BLOCKLIST)
    _said[:] = []
    check("nothing is blocked", A.is_blocked(purged, size), False)
    check("and the absence is announced",
          any("ABSENT" in s for s in _said), True)

finally:
    A.BLOCKLIST, A.BLOCKLOG, A._BLOCKED = _real_block, _real_log, _real_cache
    A.full_hash = _real_hash
    A.log = _real_logfn
    A._HASH_CACHE.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print()
if FAILURES:
    print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("all checks passed")
sys.exit(0)
