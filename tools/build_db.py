r"""Assemble one queryable library.db from every source of truth there is.

    python build_db.py                 # rebuild from scratch, safely
    python build_db.py --ask "beach"   # full-text search, to prove it works

WHAT THIS IS FOR

MASTER.csv answered "does every file have context?" and answered it well. It
cannot answer "show me every photo of Mum in Scotland before 2010", because a
29 MB CSV has no index, no joins and no way for a game to write a single answer
into it while something else is reading. This is the same facts in something
that can be asked questions and written to at the same time.

THE ONE RULE THIS FILE EXISTS TO ENFORCE

    DERIVED tables are dropped and rebuilt on every run.
    ASSERTED answers are read from answers.csv and NEVER written by this script.

Everything from a disk, a camera, a model or a geocoder is derived: if this
database is deleted, re-running costs minutes. Everything a person decided lives
in the append-only journal that this script only ever READS. There is no code
path here that can destroy a human answer, and that is deliberate rather than
incidental - it is the only data in the project that money and compute cannot
reproduce.

The build is atomic: it writes library.db.tmp and renames over library.db at the
end, so a kill leaves the previous database intact rather than a half-built one.
On this machine long jobs get killed routinely, so "the old one still works" is
worth more than "the new one is a few minutes fresher".

PRECEDENCE

A file's `place` might be claimed by a vision model, by the GPS geocoder, and by
Krish. They do not carry equal weight, and the order is the same one master_sheet
uses, for the same reasons:

    human  >  geonames  >  the vision models

so v_files shows the best available answer per field, and `tags` still holds
every opinion underneath for anyone who wants to argue with it.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
sys.path.insert(0, HERE)

from answers import Journal                        # noqa: E402
import master_sheet as MS                          # noqa: E402

OUT = os.path.join(MS.AUDIT, "library.db")

# Fields a human or a geocoder may override, resolved into one value per file.
RESOLVED = ["kind", "people", "subject", "keep", "sensitivity", "setting",
            "place", "region", "country", "era", "person", "event"]


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


def schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE files (
        path          TEXT PRIMARY KEY,
        hash          TEXT,
        side          TEXT,
        year          TEXT,
        month         TEXT,
        bytes         INTEGER,
        ext           TEXT,
        media         TEXT,
        date_taken    TEXT,
        date_source   TEXT,
        make          TEXT,
        model         TEXT,
        width         INTEGER,
        height        INTEGER,
        duration      REAL,
        lat           REAL,
        lon           REAL,
        origin_folder TEXT,
        source_root   TEXT,
        origin_path   TEXT
    );
    CREATE INDEX files_hash  ON files(hash);
    CREATE INDEX files_year  ON files(year);
    CREATE INDEX files_side  ON files(side);
    CREATE INDEX files_media ON files(media);

    -- every opinion, from every source, never resolved away
    CREATE TABLE tags (
        hash       TEXT,
        tag        TEXT,
        value      TEXT,
        source     TEXT,
        confidence REAL,
        when_      TEXT
    );
    CREATE INDEX tags_hash ON tags(hash, tag);
    CREATE INDEX tags_tag  ON tags(tag, value);

    -- the winning opinion per (hash, field), by SOURCE_RANK
    CREATE TABLE resolved (
        hash       TEXT,
        field      TEXT,
        value      TEXT,
        source     TEXT,
        confidence REAL,
        PRIMARY KEY (hash, field)
    ) WITHOUT ROWID;

    -- read from answers.csv. NEVER written by this script.
    CREATE TABLE answers (
        when_      TEXT,
        scope      TEXT,
        target     TEXT,
        field      TEXT,
        value      TEXT,
        confidence REAL,
        who        TEXT,
        note       TEXT
    );
    CREATE INDEX answers_scope ON answers(scope, target);
    """)


def load_files(db: sqlite3.Connection, inventory: str = None,
               idx: dict = None) -> int:
    idx = MS.load_hash_index() if idx is None else idx
    rows = []
    with io.open(inventory or MS.INVENTORY, encoding="utf-8", errors="replace",
                 newline="") as f:
        for r in csv.DictReader(f):
            p = r.get("LibraryPath") or ""
            if not p:
                continue
            hit = idx.get(p.lower())

            def num(k, cast):
                v = (r.get(k) or "").strip()
                try:
                    return cast(v)
                except (ValueError, TypeError):
                    return None

            rows.append((
                p, hit[1] if hit else None,
                r.get("Side"), r.get("Year"), r.get("Month"),
                num("Bytes", int), (r.get("Ext") or "").lower().lstrip("."),
                r.get("Kind"),
                r.get("DateTaken"), r.get("DateSource"),
                r.get("Make"), r.get("Model"),
                num("Width", int), num("Height", int), num("Duration", float),
                num("Lat", float), num("Lon", float),
                r.get("OriginFolder"), r.get("SourceRoot"), r.get("OriginPath"),
            ))
    db.executemany("INSERT OR REPLACE INTO files VALUES (" +
                   ",".join("?" * 20) + ")", rows)
    return len(rows)


def load_tags(db: sqlite3.Connection, store: str = None) -> int:
    p = os.path.join(store or MS.STORE, "content_tags.csv")
    if not os.path.exists(p):
        return 0
    n = 0
    batch = []
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            tag = MS.TAG_ALIAS.get(r.get("tag", ""), r.get("tag", ""))
            try:
                conf = float(r.get("confidence") or 0)
            except ValueError:
                conf = 0.0
            batch.append((r.get("hash"), tag, r.get("value"),
                          r.get("source"), conf, r.get("when")))
            if len(batch) >= 50000:
                db.executemany("INSERT INTO tags VALUES (?,?,?,?,?,?)", batch)
                n += len(batch)
                batch = []
    if batch:
        db.executemany("INSERT INTO tags VALUES (?,?,?,?,?,?)", batch)
        n += len(batch)
    return n


def resolve(db: sqlite3.Connection) -> int:
    """Pick the winning value per (hash, field) using SOURCE_RANK."""
    worst = max(MS.SOURCE_RANK.values()) + 1
    best = {}
    for h, tag, value, source, conf in db.execute(
            "SELECT hash, tag, value, source, confidence FROM tags"):
        if tag not in RESOLVED:
            continue
        rank = MS.SOURCE_RANK.get(source, worst)
        cur = best.get((h, tag))
        if cur is None or rank < cur[2] or (rank == cur[2] and conf > cur[1]):
            best[(h, tag)] = (value, conf, rank, source)
    db.executemany(
        "INSERT OR REPLACE INTO resolved VALUES (?,?,?,?,?)",
        [(h, t, v[0], v[3], v[1]) for (h, t), v in best.items()])
    return len(best)


def load_answers(db: sqlite3.Connection, store: str = None) -> int:
    """Read the journal. This function only ever reads."""
    j = Journal(store or MS.STORE)
    rows = []
    for r in j.all_rows():
        try:
            conf = float(r.get("confidence") or 1.0)
        except ValueError:
            conf = 1.0
        rows.append((r.get("when"), r.get("scope"), r.get("target"),
                     r.get("field"), r.get("value"), conf,
                     r.get("who"), r.get("note")))
    db.executemany("INSERT INTO answers VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def apply_answers(db: sqlite3.Connection) -> int:
    """Expand scoped answers onto files, overriding every machine opinion.

    Derived, and recomputed on every build: the journal records what was SAID,
    never what it implied, so changing how a scope expands never rewrites what a
    person actually answered.
    """
    written = 0
    # newest answer per key wins; ORDER BY when_ then let later rows overwrite
    for when_, scope, target, field, value, conf in db.execute(
            "SELECT when_, scope, target, field, value, confidence "
            "FROM answers ORDER BY when_"):
        if not field:
            continue
        if scope == "file":
            hashes = [(target,)]
        elif scope == "folder":
            hashes = db.execute(
                "SELECT DISTINCT hash FROM files "
                "WHERE hash IS NOT NULL AND path LIKE ? || '%'",
                (target,)).fetchall()
        elif scope == "origin":
            hashes = db.execute(
                "SELECT DISTINCT hash FROM files "
                "WHERE hash IS NOT NULL AND origin_folder = ?",
                (target,)).fetchall()
        elif scope == "cluster":
            hashes = db.execute(
                "SELECT DISTINCT hash FROM tags "
                "WHERE tag = 'cluster' AND value = ?", (target,)).fetchall()
        elif scope == "all":
            hashes = db.execute(
                "SELECT DISTINCT hash FROM files "
                "WHERE hash IS NOT NULL").fetchall()
        else:
            continue
        db.executemany(
            "INSERT OR REPLACE INTO resolved VALUES (?,?,?,'human',?)",
            [(h[0], field, value, conf) for h in hashes])
        written += len(hashes)
    return written


def build_views(db: sqlite3.Connection) -> None:
    cols = ",\n      ".join(
        "MAX(CASE WHEN r.field='{0}' THEN r.value END) AS {0}".format(f)
        for f in RESOLVED)
    db.executescript("""
    CREATE VIEW v_files AS
    SELECT f.*,
      {cols}
    FROM files f LEFT JOIN resolved r ON r.hash = f.hash
    GROUP BY f.path;
    """.format(cols=cols))

    # Full text over the words a person would actually type.
    db.executescript("""
    CREATE VIRTUAL TABLE search USING fts5(
        path, subject, place, region, country, person, event, kind, era,
        tokenize = 'porter unicode61'
    );
    """)
    db.execute("""
    INSERT INTO search (path, subject, place, region, country, person, event,
                        kind, era)
    SELECT path,
           COALESCE(subject,''), COALESCE(place,''), COALESCE(region,''),
           COALESCE(country,''), COALESCE(person,''), COALESCE(event,''),
           COALESCE(kind,''), COALESCE(era,'')
    FROM v_files
    """)


def report(db: sqlite3.Connection) -> None:
    total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print()
    print("field coverage across {:,} files:".format(total))
    for f in ["side", "year", "date_taken", "lat", "make", "duration"]:
        n = db.execute(
            "SELECT COUNT(*) FROM files WHERE {} IS NOT NULL "
            "AND {} != ''".format(f, f)).fetchone()[0]
        print("   {:<14} {:>7,}  {:>5.1f}%".format(f, n, 100.0 * n / total))
    for f in RESOLVED:
        n = db.execute(
            "SELECT COUNT(*) FROM v_files WHERE {} IS NOT NULL "
            "AND {} != ''".format(f, f)).fetchone()[0]
        if n:
            print("   {:<14} {:>7,}  {:>5.1f}%".format(f, n, 100.0 * n / total))
    a = db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    print()
    print("human answers in the journal: {:,}".format(a))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--inventory", default=None)
    ap.add_argument("--store", default=None)
    ap.add_argument("--ask", default="", help="run a full-text search and exit")
    a = ap.parse_args()

    if a.ask:
        db = connect(a.out)
        rows = db.execute(
            "SELECT path, subject, place, country FROM search "
            "WHERE search MATCH ? LIMIT 20", (a.ask,)).fetchall()
        print("{:,} shown".format(len(rows)))
        for p, s, pl, c in rows:
            print("  {:<62} {} {}".format(
                os.path.basename(p)[:60], (s or "")[:40], pl or c or ""))
        return

    t0 = time.time()
    tmp = a.out + ".tmp"
    for leftover in (tmp, tmp + "-wal", tmp + "-shm"):
        if os.path.exists(leftover):
            os.remove(leftover)

    db = connect(tmp)
    schema(db)
    print("files    : {:,}".format(load_files(db, a.inventory)))
    print("tags     : {:,}".format(load_tags(db, a.store)))
    print("resolved : {:,}".format(resolve(db)))
    print("answers  : {:,} read from the journal".format(
        load_answers(db, a.store)))
    print("applied  : {:,} file-fields set by a human".format(apply_answers(db)))
    build_views(db)
    db.commit()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()

    for ext in ("-wal", "-shm"):
        if os.path.exists(tmp + ext):
            os.remove(tmp + ext)
    os.replace(tmp, a.out)

    db = connect(a.out)
    report(db)
    db.close()
    print()
    print("wrote {} in {:.0f}s".format(a.out, time.time() - t0))


if __name__ == "__main__":
    main()
