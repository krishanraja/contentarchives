r"""The enrichment store: what we know about a file, keyed by its content.

EVERYTHING IS KEYED ON CONTENT HASH, NEVER ON PATH.

This is the load-bearing decision. Paths are not identity - they are a fact
about where a file happens to sit this week. In this project alone, paths have
been invalidated by a Personal/Communal split, a rename of the library root, a
move of every chronology tree into Media\, a D:->H: mirror, and 21,649
deletions. Any enrichment keyed on paths would have died at the first of those,
and died SILENTLY, which is the expensive way.

A content hash survives all of it. It also gives three things free:

  - re-ingest inheritance: the same photo arriving again from another source
    arrives already tagged
  - duplicate collapse: two paths, one hash, one set of tags
  - portability: the store is meaningful on another machine, or beside a copy
    of the library on different hardware

THE PROVENANCE RULE

Every claim records WHO said it and HOW SURE they were. A model's guess and a
human's confirmation must never be indistinguishable, because the whole point
of the swipe game is to progressively upgrade the former into the latter. A
store that flattens them can never tell you what still needs asking.

    source:     model:haiku | model:opus | human | derived | metadata
    confidence: 0.0 - 1.0   (human answers are 1.0)

MERGES ARE RECORDED, NOT APPLIED

When two people turn out to be one, person B is marked merged_into A. Nothing
is rewritten. If the merge was wrong - and with faces it sometimes will be -
it is one row to reverse rather than an unpickable knot of overwritten ids.

    from store import Store
    s = Store(r"D:\_PhotoAudit\enrichment")
    s.tag(h, "kind", "screenshot", source="model:haiku", confidence=0.94)
    s.observe(h, person_id=142, source="human")
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import threading

TAGS = "content_tags.csv"
PEOPLE = "people.csv"
OBS = "observations.csv"
MERGES = "merge_suggestions.csv"
FILES = "files.csv"

_LOCK = threading.Lock()


def content_hash(path: str, chunk: int = 8 * 1024 * 1024) -> str:
    """blake2b-256 of the whole file.

    Whole-file, not head+tail. A cheap signature is fine for building a
    shortlist and is not fine for identity: two videos from the same camera
    can share a header and differ entirely, and this hash is what every tag
    in the store hangs off.
    """
    h = hashlib.blake2b(digest_size=32)
    p = path if path.startswith("\\\\?\\") else "\\\\?\\" + path
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


class Store:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self._ensure(FILES, ["hash", "path", "bytes", "seen"])
        self._ensure(TAGS, ["hash", "tag", "value", "source", "confidence", "when"])
        self._ensure(PEOPLE, ["person_id", "display_label", "name", "status",
                              "observations", "first_seen", "when"])
        self._ensure(OBS, ["hash", "person_id", "bbox", "source", "confidence", "when"])
        self._ensure(MERGES, ["person_a", "person_b", "reason", "confidence",
                              "status", "when"])

    # ---------- plumbing ----------
    def _p(self, name: str) -> str:
        return os.path.join(self.root, name)

    def _ensure(self, name: str, cols: list[str]) -> None:
        p = self._p(name)
        if not os.path.exists(p):
            with open(p, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(cols)

    def _append(self, name: str, row: list) -> None:
        # Append-only, flushed and fsynced. The store is written by long batch
        # jobs that get killed - by a memory watchdog here, routinely - and a
        # buffered write loses the work that was already paid for.
        with _LOCK:
            with open(self._p(name), "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
                f.flush()
                os.fsync(f.fileno())

    def _read(self, name: str) -> list[dict]:
        with open(self._p(name), newline="", encoding="utf-8", errors="replace") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _now() -> str:
        return dt.datetime.now().isoformat(timespec="seconds")

    # ---------- files ----------
    def register(self, h: str, path: str, size: int) -> None:
        self._append(FILES, [h, path, size, self._now()])

    def known_hashes(self) -> set[str]:
        """Hashes already tagged - so a batch run resumes instead of re-paying."""
        return {r["hash"] for r in self._read(TAGS)}

    # ---------- tags ----------
    def tag(self, h: str, tag: str, value: str, source: str,
            confidence: float = 1.0) -> None:
        self._append(TAGS, [h, tag, value, source, f"{confidence:.2f}", self._now()])

    def tags_for(self, h: str) -> dict[str, tuple[str, str, float]]:
        """Best claim per tag: a human answer always beats a model's."""
        best: dict[str, tuple[str, str, float]] = {}
        for r in self._read(TAGS):
            if r["hash"] != h:
                continue
            conf = float(r["confidence"] or 0)
            human = r["source"] == "human"
            cur = best.get(r["tag"])
            if cur is None or (human and cur[1] != "human") or \
               (human == (cur[1] == "human") and conf > cur[2]):
                best[r["tag"]] = (r["value"], r["source"], conf)
        return best

    # ---------- people ----------
    def new_person(self) -> int:
        people = self._read(PEOPLE)
        pid = max((int(r["person_id"]) for r in people), default=0) + 1
        self._append(PEOPLE, [pid, f"Person {pid}", "", "active", 0,
                              self._now(), self._now()])
        return pid

    def observe(self, h: str, person_id: int, source: str,
                confidence: float = 1.0, bbox: str = "") -> None:
        self._append(OBS, [h, person_id, bbox, source, f"{confidence:.2f}",
                           self._now()])

    def name_person(self, person_id: int, name: str) -> None:
        """Naming is a human act, so it is recorded as a new row, not an edit.
        The history of what a person was called stays visible."""
        rows = self._read(PEOPLE)
        cur = next((r for r in rows if int(r["person_id"]) == person_id), None)
        label = cur["display_label"] if cur else f"Person {person_id}"
        obs = cur["observations"] if cur else 0
        first = cur["first_seen"] if cur else self._now()
        self._append(PEOPLE, [person_id, label, name, "active", obs, first,
                              self._now()])

    def suggest_merge(self, a: int, b: int, reason: str, confidence: float) -> None:
        self._append(MERGES, [a, b, reason, f"{confidence:.2f}", "pending",
                              self._now()])

    def resolve_merge(self, a: int, b: int, accept: bool) -> None:
        self._append(MERGES, [a, b, "resolved by human", "1.00",
                              "accepted" if accept else "rejected", self._now()])
        if accept:
            rows = self._read(PEOPLE)
            cur = next((r for r in rows if int(r["person_id"]) == b), None)
            if cur:
                self._append(PEOPLE, [b, cur["display_label"], cur["name"],
                                      f"merged_into:{a}", cur["observations"],
                                      cur["first_seen"], self._now()])

    def people(self, include_merged: bool = False) -> list[dict]:
        latest: dict[str, dict] = {}
        for r in self._read(PEOPLE):
            latest[r["person_id"]] = r          # append-only: last row wins
        out = list(latest.values())
        if not include_merged:
            out = [r for r in out if not r["status"].startswith("merged_into")]
        return out
