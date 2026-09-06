"""Three-tier duplicate detection: cheap to rule out, expensive to confirm.

See docs/LEARNINGS.md rule 7.

    1. size            - from the directory or archive index, no I/O.
                         A size that exists nowhere in the library CANNOT be a
                         duplicate. This clears most candidates for free.
    2. head+tail sig   - first and last 256 KB. Rules out most size collisions
                         after reading half a megabyte.
    3. whole-file hash - the ONLY thing permitted to *declare* a duplicate.

Filename is never part of the decision. Two different files sharing a name and an
exact byte count are rare but real, and the failure mode is silent data loss.
"""

from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from pathlib import Path

__all__ = ["Index", "file_signature", "file_hash", "HashCache"]

CHUNK = 256 * 1024
READ_BLOCK = 4 * 1024 * 1024


def _long(p) -> str:
    s = str(p)
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def file_signature(path, size: int | None = None) -> str | None:
    """Head+tail signature. Cheap enough to run on everything, strong enough to
    rule out. Never strong enough to rule *in*."""
    try:
        if size is None:
            size = os.path.getsize(_long(path))
        h = hashlib.blake2b(digest_size=16)
        with open(_long(path), "rb", buffering=0) as fh:
            h.update(fh.read(CHUNK))
            if size > CHUNK * 2:
                fh.seek(-CHUNK, os.SEEK_END)
                h.update(fh.read(CHUNK))
        return h.hexdigest()
    except OSError:
        return None


def file_hash(path) -> str | None:
    """Whole-file hash. The only basis on which a duplicate may be declared."""
    try:
        h = hashlib.blake2b(digest_size=32)
        with open(_long(path), "rb", buffering=0) as fh:
            while True:
                block = fh.read(READ_BLOCK)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


class HashCache:
    """Persistent hash cache for files that never change.

    Library files are immutable once filed, so re-deriving their hashes every run
    costs gigabytes of reads for no new information. Keyed on (path, size) so a
    file that *does* change simply misses the cache rather than returning a stale
    answer.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._mem: dict[tuple[str, int], str] = {}
        self._pending: list[list] = []
        if self.path.exists():
            with open(self.path, newline="", encoding="utf-8") as fh:
                for row in csv.reader(fh):
                    if len(row) == 3:
                        try:
                            self._mem[(row[0], int(row[1]))] = row[2]
                        except ValueError:
                            continue

    def get(self, path, size: int) -> str | None:
        key = (str(path), size)
        cached = self._mem.get(key)
        if cached:
            return cached
        digest = file_hash(path)
        if digest:
            self._mem[key] = digest
            self._pending.append([str(path), size, digest])
            if len(self._pending) >= 50:
                self.flush()
        return digest

    def flush(self) -> None:
        if not self._pending:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(self._pending)
        self._pending.clear()


class Index:
    """Size-keyed index of everything already held.

    Built from a directory walk, then kept current incrementally - a full rewalk
    of a large library costs most of a run's life when the process is being
    killed every few minutes.
    """

    def __init__(self, hash_cache: HashCache | None = None):
        self.by_size: dict[int, list[str]] = defaultdict(list)
        self.hashes = hash_cache

    @classmethod
    def from_roots(cls, roots, hash_cache: HashCache | None = None) -> "Index":
        idx = cls(hash_cache)
        for root in roots:
            for dirpath, _, names in os.walk(root):
                for name in names:
                    full = os.path.join(dirpath, name)
                    try:
                        idx.by_size[os.path.getsize(full)].append(full)
                    except OSError:
                        continue
        return idx

    def add(self, path, size: int | None = None) -> None:
        if size is None:
            size = os.path.getsize(path)
        self.by_size[size].append(str(path))

    def __len__(self) -> int:
        return sum(len(v) for v in self.by_size.values())

    # ---------------------------------------------------------------- queries

    def size_is_novel(self, size: int) -> bool:
        """True if nothing held has this exact byte count, so the candidate
        cannot possibly be a duplicate. No I/O."""
        return size not in self.by_size

    def find_duplicate(self, path, size: int | None = None, max_candidates: int = 8):
        """Return the held path whose content is identical, or None.

        Tier 1 clears novel sizes instantly. Tier 2 rules out size collisions
        cheaply. Tier 3 is the only thing that returns a match.
        """
        if size is None:
            size = os.path.getsize(_long(path))
        candidates = self.by_size.get(size)
        if not candidates:
            return None

        sig = file_signature(path, size)
        if sig is None:
            return None

        shortlist = []
        for cand in candidates[:max_candidates]:
            if file_signature(cand, size) == sig:
                shortlist.append(cand)
        if not shortlist:
            return None

        mine = self.hashes.get(path, size) if self.hashes else file_hash(path)
        if mine is None:
            return None
        for cand in shortlist:
            theirs = self.hashes.get(cand, size) if self.hashes else file_hash(cand)
            if theirs == mine:
                return cand
        return None
