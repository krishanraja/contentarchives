r"""The only sanctioned way to delete anything outside autopilot.

THE RULE: nothing is deleted unless, at the moment of deletion, either

  (a) a SURVIVING COPY is proven to exist - a different inode, holding
      byte-identical content, re-hashed right now and readable; or
  (b) the file is GENUINE GARBAGE by a narrow, named category.

Everything else raises. There is no third path, no "probably fine", and no
flag to override it.

WHY IT IS BUILT THIS WAY

Every near-miss on this project came from a deletion justified by something
that was true EARLIER:

  - a path-substring rule deleted 45 irreplaceable personal files
  - `Photos.zip` looked redundant: 19 of its 20 videos were, and the 20th was
    the only full-quality copy of a 323.8 MB video the library held as a
    15.9 MB truncation
  - a triage report listing 6,217 redundant files was written while an ingest
    was still running, so by the time it was acted on the library had moved

So a report is never evidence. An index is never evidence. Only the filesystem
as it is at the instant of the unlink is evidence, and this module re-reads it
every time even when the caller is certain.

THE INODE CHECK IS NOT OPTIONAL

Two paths can hold identical content because they are hardlinks - one set of
bytes wearing two names. Deleting one then frees nothing, and if the caller
believed it had two copies it now has none in the way that matters. So the
survivor must be a DIFFERENT inode, not merely a different path. This was
measured on 2026-09-07: 322.5 GB of D: is hardlinked, and a size-based reading
of the same drive suggested 300 GB of reclaim that did not exist.

GARBAGE IS A CLOSED LIST

Not "small files", not "screenshots", not "looks like junk". A category earns
its place only if the file cannot carry irreplaceable content by construction:
a GoPro .lrv is a proxy generated beside its own full-resolution .mp4; a .thm
is a thumbnail stub; a zero-byte file has nothing in it. Screenshots are NOT
here - they may be the only record of something, so they are moved for review,
never deleted by a machine.

    from guarded_delete import delete_with_surviving_copy, delete_garbage
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os

JOURNAL = r"D:\_PhotoAudit\user-directed-deletions.csv"

# Categories where the file cannot, by construction, be the only copy of
# anything irreplaceable. Deliberately short. Adding to it is a decision.
GARBAGE = {
    "gopro-proxy":   (".lrv",),      # generated beside the full-res .mp4
    "thumbnail-stub": (".thm",),     # camera thumbnail, not an image
    "empty":         (),             # zero bytes, checked separately
}


class DeletionRefused(Exception):
    pass


def _lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def _hash(path: str) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(_lp(path), "rb") as f:
        while True:
            b = f.read(8 * 1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _journal(path: str, size: int, reason: str, evidence: str) -> None:
    new = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["Path", "Bytes", "Reason", "Evidence", "When"])
        w.writerow([path, size, reason, evidence,
                    dt.datetime.now().isoformat(timespec="seconds")])
        f.flush()
        os.fsync(f.fileno())


def delete_with_surviving_copy(victim: str, survivor: str, reason: str) -> int:
    """Delete `victim` only if `survivor` provably holds the same bytes.

    Re-verified now, from the filesystem, regardless of what the caller thinks
    it knows. Returns bytes freed. Raises DeletionRefused on any doubt.
    """
    if not os.path.exists(_lp(victim)):
        raise DeletionRefused(f"victim already gone: {victim}")
    if not os.path.exists(_lp(survivor)):
        raise DeletionRefused(f"SURVIVOR MISSING - refusing: {survivor}")

    vs = os.stat(_lp(victim))
    ss = os.stat(_lp(survivor))

    if (vs.st_dev, vs.st_ino) == (ss.st_dev, ss.st_ino):
        raise DeletionRefused(
            f"same inode - these are hardlinks, not two copies: {victim}")
    if vs.st_size != ss.st_size:
        raise DeletionRefused(
            f"sizes differ ({vs.st_size} vs {ss.st_size}) - not a copy: {victim}")

    if _hash(victim) != _hash(survivor):
        raise DeletionRefused(f"content differs despite equal size: {victim}")

    # survivor must still be readable end-to-end; a copy that cannot be read
    # is not a copy
    try:
        with open(_lp(survivor), "rb") as f:
            f.seek(max(0, ss.st_size - 4096))
            f.read()
    except OSError as e:
        raise DeletionRefused(f"survivor unreadable ({e}): {survivor}")

    os.remove(_lp(victim))
    _journal(victim, vs.st_size, reason,
             f"surviving copy {survivor} verified at deletion: same blake2b-256, "
             f"{vs.st_size:,} bytes, different inode")
    return vs.st_size


def delete_garbage(path: str, category: str, reason: str) -> int:
    """Delete a file that cannot be the only copy of anything that matters."""
    if category not in GARBAGE:
        raise DeletionRefused(f"unknown garbage category '{category}': {path}")
    if not os.path.exists(_lp(path)):
        raise DeletionRefused(f"already gone: {path}")
    st = os.stat(_lp(path))

    if category == "empty":
        if st.st_size != 0:
            raise DeletionRefused(f"not empty ({st.st_size} bytes): {path}")
    else:
        ext = os.path.splitext(path)[1].lower()
        if ext not in GARBAGE[category]:
            raise DeletionRefused(
                f"extension {ext} is not in category '{category}': {path}")
        if category == "gopro-proxy":
            # a proxy is only garbage while its full-resolution original is there
            for cand in (path[:-4] + ".MP4", path[:-4] + ".mp4"):
                if os.path.exists(_lp(cand)):
                    break
            else:
                raise DeletionRefused(
                    f"no full-resolution .MP4 beside this proxy - refusing: {path}")

    os.remove(_lp(path))
    _journal(path, st.st_size, reason, f"garbage category '{category}', verified")
    return st.st_size
