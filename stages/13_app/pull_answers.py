r"""Bring what the family said in the app into the journal. Safe to run any number of times.

    python stages/13_app/pull_answers.py             # dry run: what would be recorded
    python stages/13_app/pull_answers.py --apply     # record, then mark each cloud row

The app's `answers` table is the system of record until this runs, so the app
never waits on this machine (Krish, 2026-10-04: "always on ... no reliance on
a local drive"). When it does run, every answer reaches answers.csv through
ingest_game_answers.py - the same cursor, name folding, field whitelist and
share-set check as every other game - under the name of the relative who gave
it.

WHY "OLDER THAN TEN MINUTES"

The app lets anyone undo an answer for ten minutes. An answer pulled inside
that window could be undone in the app after it had already reached the
append-only journal, where undo means appending a correction nobody asked for.
So nothing younger than the window is taken.

ONE CLOUD ROW, MANY JOURNAL ROWS

"Also label the other 23 photos from that day" is one tap and one cloud row
carrying 24 hashes. The journal records what was said about each photograph,
so it becomes 24 file-scope rows - ids `app-<uuid>-<n>`, so the cursor knows
each one - and the cloud row is `ingested` only if every one of them was.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
from blocklist import blocked_hashes                             # noqa: E402
from share_set import share_set, open_ro                         # noqa: E402

UNDO_MINUTES = 10
FIELD = {"person": "person", "unidentifiable": "unidentifiable",
         "place": "place", "approx_year": "approx_year"}


def expand(answers: list) -> list:
    """Cloud rows -> structured journal rows for ingest_game_answers.py."""
    rows = []
    for a in answers:
        uid = a["id"]
        if a["scope"] == "cluster":
            rows.append({"id": "app-" + uid, "scope": "cluster", "target": a["target"],
                         "field": FIELD.get(a["field"], a["field"]), "value": a["value"],
                         "who": a["who"]})
        else:
            for n, h in enumerate(a.get("hashes") or [a["target"]]):
                rows.append({"id": "app-{}-{}".format(uid, n), "scope": "file", "target": h,
                             "field": FIELD.get(a["field"], a["field"]), "value": a["value"],
                             "who": a["who"]})
    return rows


def verdicts(answers: list, status: dict, cursor: set = frozenset()) -> dict:
    """cloud id -> (status, reason): ingested only if EVERY journal row was.

    A row already in the ingest CURSOR counts as ingested. Without that, a run
    that recorded answers and then died before marking the cloud would leave
    them `new` forever: the next ingest skips them as already done, reports
    nothing about them, and nothing would ever mark them.
    """
    out = {}
    for a in answers:
        uid = a["id"]
        ids = [r["id"] for r in expand([a])]
        mine = {k: status.get(k) or ({"status": "ingested", "reason": ""} if k in cursor else None)
                for k in ids}
        if any(v is None for v in mine.values()):
            continue
        bad = [v["reason"] for v in mine.values() if v["status"] != "ingested"]
        out[uid] = ("refused", "; ".join(sorted(set(bad)))[:300]) if bad else ("ingested", None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--store", default=r"D:\_enrichment")
    ap.add_argument("--backup", default=None, help="passed through to the ingest")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    from cloud import Cloud
    c = Cloud()
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=UNDO_MINUTES)).isoformat()
    answers = c.select("answers", "select=*&status=eq.new&at=lt.{}&order=at.asc".format(
        cutoff.replace("+", "%2B")))
    print("app answers waiting (older than {} min): {:,}".format(UNDO_MINUTES, len(answers)))

    skips = c.select("skips", "select=group_id,who")
    many = collections.Counter(s["group_id"] for s in skips if not s["group_id"].startswith("story:"))
    stuck = [g for g, n in many.most_common() if n >= 3]
    if stuck:
        print("faces 3+ relatives did not know ({}): {}".format(len(stuck), ", ".join(stuck[:12])))
    if not answers:
        return 0

    rows = expand(answers)
    db = open_ro(a.db)
    try:
        shared, _ = share_set(db, blocked_hashes())
    finally:
        db.close()

    tmp = tempfile.mkdtemp(prefix="app-pull-")
    rp, al, st = (os.path.join(tmp, n) for n in ("rows.json", "allowed.txt", "status.json"))
    io.open(rp, "w", encoding="utf-8").write(json.dumps(rows))
    io.open(al, "w", encoding="utf-8").write("\n".join(shared))
    cmd = [sys.executable, stagepath.script("ingest_game_answers.py"),
           "--rows", rp, "--store", a.store, "--tags", os.path.join(a.store, "content_tags.csv"),
           "--cursor", os.path.join(a.store, "game-ingest-cursor.json"),
           "--allowed", al, "--status-out", st]
    if a.backup:
        cmd += ["--backup", a.backup]
    if a.apply:
        cmd.append("--apply")
    rc = subprocess.call(cmd)
    if rc != 0:
        print("STOPPING: the ingest exited {} - no cloud row is marked".format(rc))
        return rc
    if not a.apply:
        return 0
    status = json.load(io.open(st, encoding="utf-8")) if os.path.exists(st) else {}
    cpath = os.path.join(a.store, "game-ingest-cursor.json")
    cursor = set(json.load(io.open(cpath, encoding="utf-8")).get("ingested", [])) \
        if os.path.exists(cpath) else set()
    marked = collections.Counter()
    for uid, (s, why) in verdicts(answers, status, cursor).items():
        c.patch("answers", "id=eq." + uid, {"status": s, "reason": why})
        marked[s] += 1
    print("cloud rows marked: {}".format(dict(marked)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
