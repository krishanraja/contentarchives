r"""Freeze the family's record every night: what they said, and what is known
about every photograph. Run by the nightly workflow after the index is built.

    python stages/13_app/export_record.py              # tonight's export, verified
    python stages/13_app/export_record.py --keep 14    # how many nights to keep

WHY (Krish, 2026-10-16)

"I expect all this to be done automatically in the future we just use the app.
The external D (currently F) Drive should just be a backup, nothing should rely
on this external drive." The cloud is the record: the app writes every answer
into it, and the index is built here from Drive. Supabase backs the whole
database up each night. This adds a frozen, portable copy that needs no PC:

  answers    every row of `answers` - what the family said in the app, undone
             rows included, with their status
  journal    the library's journal, imported once (LIBRARY-EXPORT.md)
  catalogue  one row per photograph: how to find it on BOTH copies (its md5,
             which identifies it on the backup drive; its Drive id and path on
             H:) and everything known about it, with the date and place the app
             shows and where each came from

Asked whether the cloud should move files into year folders when the family
dates them, Krish said no, "the app organizes. But set this up so that in the
future, I can use the enriched information to resegment in both the external
drive and the H drive." The catalogue is that input. Its columns, and why each
is there, are in CATALOGUE.md.

Each name is one gzip'd CSV in `record_exports` (migration 0017), keyed by day:
a second run on the same day replaces that day's copy, and only the newest
--keep days are kept. Every copy is read back after it is committed and checked
against its sha256 and its row count, or the run fails. The library machine
copies the newest onto the backup drive whenever that drive is connected
(backup_to_drive.py); nothing here waits on it.

THIS LOG IS PUBLIC (the workflow's log on a public repository): numbers only,
through cloud_enrich.say().
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import os
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
from cloud_enrich import say                                     # noqa: E402

KEEP = 14

# name -> the query that makes it. Ordered, so the same database gives the same
# bytes and a night with nothing new is visibly identical to the one before.
QUERIES = {
    "answers": """
        select id, at, client_at, who, scope, target, field, value,
               array_to_string(hashes, ' ') as hashes, status, reason
        from answers order by at, id""",
    "journal": """
        select id, at, who, scope, target, field, value, confidence, note
        from journal order by at, id""",
    # The date and place the app shows, by the app's own precedence
    # (web/lib/when.ts whenText; migrations 0011, 0012): the family's answer,
    # then the camera's clock, then the year folder, then the library's
    # estimate - each with its source, so a re-sort can choose how far to trust
    # it. People come from the live photo_people view (who the family said is in
    # it, counted as the app counts it), not the search copy, which can lag.
    "catalogue": """
        select p.hash, p.md5, p.drive_id, p.rel_path, p.media,
               case when p.rel_path like 'Media/Communal/%' then 'Communal'
                    when p.rel_path like 'Media/Personal/%' then 'Personal'
                    else '' end as side,
               p.visible, p.hidden, p.hidden_by,
               coalesce(p.family_when, to_char(p.taken_at at time zone 'UTC', 'YYYY-MM-DD'),
                        p.year::text, p.approx_year) as best_when,
               case when p.family_when is not null then 'family'
                    when p.taken_at is not null then 'camera'
                    when p.year is not null then 'folder'
                    when p.approx_year is not null then 'library'
                    else '' end as when_source,
               p.when_year, p.family_when, p.taken_at, p.year, p.approx_year,
               coalesce(p.family_place, p.place) as best_place,
               case when p.family_place is not null then 'family'
                    when p.place is not null then 'index'
                    else '' end as place_source,
               p.family_place, p.place, p.region, p.country, p.lat, p.lon,
               pp.people, p.day_key, p.description, p.objects, p.activity,
               p.occasion, p.mood, p.width, p.height, p.source, p.updated_at
        from photos p
        left join (select hash, string_agg(distinct name, '; ' order by name) as people
                   from photo_people group by hash) pp on pp.hash = p.hash
        order by p.hash""",
}


def to_csv_gz(cur) -> tuple:
    """(gzip bytes, data rows) for the rows a cursor holds, header first.

    mtime=0 so the same rows always give the same bytes and the same sha256.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([c.name for c in cur.description])
    n = 0
    for row in cur:
        w.writerow(["" if v is None else v for v in row])
        n += 1
    return gzip.compress(buf.getvalue().encode("utf-8"), mtime=0), n


def rows_in(body: bytes) -> int:
    """Data rows in a gzip'd CSV, read back the way a reader would read it."""
    text = gzip.decompress(body).decode("utf-8")
    return sum(1 for _ in csv.reader(io.StringIO(text))) - 1


def export(db, day: dt.date, keep: int = KEEP) -> dict:
    """Write tonight's copies, commit, read them back. -> {name: rows}."""
    made = {}
    with db.cursor() as cur:
        for name, sql in QUERIES.items():
            cur.execute(sql)
            body, n = to_csv_gz(cur)
            made[name] = (n, body, hashlib.sha256(body).hexdigest())
        for name, (n, body, sha) in made.items():
            cur.execute(
                """insert into record_exports (day, name, rows, bytes, sha256, body)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (day, name) do update set rows = excluded.rows,
                     bytes = excluded.bytes, sha256 = excluded.sha256,
                     body = excluded.body, made_at = now()""",
                (day, name, n, len(body), sha, body))
        cur.execute(
            """delete from record_exports where day not in (
                 select distinct day from record_exports order by day desc limit %s)""",
            (keep,))
        pruned = cur.rowcount
    db.commit()
    problems = verify(db, day, {k: (v[0], v[2]) for k, v in made.items()})
    if problems:
        raise SystemExit("STOPPING: the export did not read back: {} problem(s)".format(len(problems)))
    say("record export", answers=made["answers"][0], journal=made["journal"][0],
        catalogue=made["catalogue"][0],
        bytes=sum(len(v[1]) for v in made.values()), pruned=pruned)
    return {k: v[0] for k, v in made.items()}


def verify(db, day: dt.date, want: dict = None) -> list:
    """Problems with a day's copies; empty means every one reads back whole.

    Each body must match the sha256 stored beside it and hold the rows it
    claims; given `want` ({name: (rows, sha256)}), it must also be what was just
    written. Problems are names and counts only - never content - because the
    caller's log is public.
    """
    problems = []
    with db.cursor() as cur:
        cur.execute("select name, rows, sha256, body from record_exports where day = %s", (day,))
        got = {r[0]: r[1:] for r in cur.fetchall()}
    for name in QUERIES:
        if name not in got:
            problems.append("{}: missing".format(name))
            continue
        rows, sha, body = got[name]
        body = bytes(body)
        if hashlib.sha256(body).hexdigest() != sha:
            problems.append("{}: sha256 does not match its body".format(name))
            continue
        try:
            n = rows_in(body)
        except (OSError, EOFError, UnicodeDecodeError):
            problems.append("{}: body does not decompress".format(name))
            continue
        if n != rows:
            problems.append("{}: holds {} rows, claims {}".format(name, n, rows))
        if want and name in want and (rows, sha) != want[name]:
            problems.append("{}: is not what was just written".format(name))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", type=int, default=KEEP)
    a = ap.parse_args()
    if a.keep < 1:
        print("STOPPING: --keep must be at least 1")
        return 1
    if not os.environ.get("DATABASE_URL"):
        print("STOPPING: DATABASE_URL is not set")
        return 1
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as db:
        export(db, dt.datetime.now(dt.timezone.utc).date(), a.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
