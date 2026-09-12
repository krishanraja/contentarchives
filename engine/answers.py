r"""The answers a person gave. The one thing here that cannot be recomputed.

    from answers import Journal
    j = Journal(r"D:\_enrichment")
    j.record("cluster", "c17", "person", "Mum")        # labels every photo of her
    j.record("folder", r"...\Media\Personal\2016\2016-08", "event", "Italy")
    j.record("file", "3f9a...", "keep", "no")

WHY THIS IS A SEPARATE FILE FROM EVERYTHING ELSE

Every other artefact in this project is derived, and derived means disposable.
Thumbnails rebuild. Hashes recompute. Classification can be re-bought - the
whole library cost about $27. The inventory is read back off the disk. If any of
it burned down tomorrow the cost would be time and money, both bounded.

A person's judgement about who is in a photograph is not like that. It exists
nowhere else in the world. If the answers table is dropped by a rebuild, no
amount of money or compute brings it back - it has to be asked again, question
by question, of a human being who already answered it once.

So the answers are NOT a table in the database. They are an append-only CSV that
the database is built FROM. The database can be deleted at any time, with no
loss. That inversion is the whole design: make the irreplaceable thing the
simplest, dumbest, most portable artefact in the system - a text file that any
tool on any machine in any decade can read - and let the clever, fragile,
regenerable things depend on it rather than contain it.

SCOPES, BECAUSE ONE ANSWER SHOULD LABEL THOUSANDS OF FILES

The expensive part of enrichment is not storage, it is the person's attention.
So an answer names a SCOPE rather than a file wherever it can:

    cluster   a face cluster      -> every photograph that person appears in
    folder    a library folder    -> everything filed under it, recursively
    origin    an origin folder    -> everything that came from that source
    file      one content hash    -> exactly one file's worth of content
    all       the whole library   -> a global correction

The Personal/Communal split already proved the principle at folder level: "74,000
file judgements become a few hundred folder judgements." Naming 50 face clusters
is the same trick applied to the 51,797 images that have a face in them.

Expanding a scope to a set of files is DERIVED and happens in build_db.py. The
journal stores what was actually said, not its consequences, so re-deciding how
a scope expands never rewrites history.

CORRECTIONS ARE APPENDED, NEVER EDITED

Changing an answer appends a new row. The reader takes the LAST row for a given
(scope, target, field), so the newest answer wins and the older one stays
visible. An append-only journal can be reconstructed after any crash, can be
diffed, and can be read by a person asking "when did I decide that, and what did
I think before?"
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import threading

JOURNAL = "answers.csv"
COLS = ["when", "scope", "target", "field", "value", "confidence", "who", "note"]
SCOPES = ("file", "folder", "origin", "cluster", "all")

_LOCK = threading.Lock()


class Journal:
    """Append-only record of what a human decided."""

    def __init__(self, root: str, who: str = "krish"):
        self.path = os.path.join(root, JOURNAL)
        self.who = who
        os.makedirs(root, exist_ok=True)
        if not os.path.exists(self.path):
            with io.open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(COLS)

    def record(self, scope: str, target: str, field: str, value: str,
               confidence: float = 1.0, note: str = "") -> None:
        """Append one answer. Flushed and fsynced before returning.

        fsync on every single answer, unlike the derived bulk writes, because
        this is the file whose loss cannot be undone by re-running anything. One
        human answer is worth more than the microseconds.
        """
        if scope not in SCOPES:
            raise ValueError("scope must be one of " + ", ".join(SCOPES))
        row = [dt.datetime.now().isoformat(timespec="seconds"), scope,
               target, field, value, "{:.2f}".format(float(confidence)),
               self.who, note]
        with _LOCK:
            with io.open(self.path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
                f.flush()
                os.fsync(f.fileno())

    def all_rows(self) -> list:
        """Every answer ever given, oldest first, corrections included."""
        if not os.path.exists(self.path):
            return []
        with io.open(self.path, encoding="utf-8", errors="replace",
                     newline="") as f:
            return list(csv.DictReader(f))

    def current(self) -> dict:
        """(scope, target, field) -> row, keeping only the newest answer.

        A correction is an append, so the last row for a key is the live one.
        """
        out = {}
        for r in self.all_rows():
            out[(r["scope"], r["target"], r["field"])] = r
        return out

    def answered(self, scope: str, field: str) -> set:
        """Targets already answered for a field - so a game never asks twice."""
        return {t for (s, t, f) in self.current() if s == scope and f == field}
