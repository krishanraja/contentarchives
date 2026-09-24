r"""Group photographs into EVENTS, because nobody remembers a file.

    python build_events.py                  # report, write nothing
    python build_events.py --apply
    python build_events.py --ask "the trip to Lisbon"

WHY THIS EXISTS

`embed_descriptions.py` answers a question with twelve photographs. But "the
Lisbon trip" is not twelve photographs, it is four days and two hundred of
them, and a tool that returns a scattering of frames from the middle of it has
answered a narrower question than the one asked.

WHAT AN EVENT IS HERE, AND WHAT IT IS NOT

It is a run of photographs with no gap longer than `--gap` hours between
consecutive shots. That is all. It is NOT the `occasion` field, which is a
CATEGORY - "everyday" (28,549), "travel" (23,289), "party" (9,041) - and
answers what KIND of thing this was, never which one. Grouping on it would put
every party since 2008 in one bucket.

Time is the only signal that separates one wedding from another, and it is
cheap: a wedding is a Saturday, a holiday is a week, and the hours between
them are empty. Place and people and occasion then DESCRIBE the event that
time has already found.

WHAT IT CANNOT SEE, AND SAYS SO

48,196 of 85,480 files carry a real `date_taken` - 56%. The rest have a year
from the chronology and no clock, so they cannot be placed in a run at all:
scans, WhatsApp forwards, anything whose EXIF was stripped on the way. They are
counted and reported, never silently dropped, because an event list that
quietly covers half the library is this project's recurring failure in
friendlier clothing.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                               # noqa: E402

DB = os.path.join(P.AUDIT, "library.db")
OUT = os.path.join(P.AUDIT, "EVENTS.json")


def load(db, gap_hours, min_files):
    cur = db.execute(
        "SELECT hash, path, date_taken FROM files "
        "WHERE date_taken <> '' AND hash IS NOT NULL ORDER BY date_taken")
    rows = []
    for h, p, d in cur:
        try:
            rows.append((dt.datetime.strptime(d, "%Y-%m-%d %H:%M:%S"), h, p))
        except ValueError:
            continue
    total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    gap = dt.timedelta(hours=gap_hours)
    runs, cur_run = [], []
    for r in rows:
        if cur_run and r[0] - cur_run[-1][0] > gap:
            runs.append(cur_run)
            cur_run = []
        cur_run.append(r)
    if cur_run:
        runs.append(cur_run)
    kept = [r for r in runs if len(r) >= min_files]
    return rows, runs, kept, total


def describe(db, run):
    """What this event WAS, from the files in it. Majorities, not guesses."""
    hs = [h for _, h, _ in run]
    q = ",".join("?" * len(hs))
    place = collections.Counter()
    occasion = collections.Counter()
    people = collections.Counter()
    for f, v in db.execute(
            "SELECT field, value FROM resolved WHERE hash IN ({}) "
            "AND field IN ('place','country','occasion')".format(q), hs):
        (place if f in ("place", "country") else occasion)[v] += 1
    for (v,) in db.execute(
            "SELECT person FROM photo_people WHERE hash IN ({})".format(q), hs):
        if v:
            people[v] += 1
    desc = db.execute(
        "SELECT value FROM resolved WHERE hash IN ({}) AND field='description' "
        "ORDER BY length(value) DESC LIMIT 1".format(q), hs).fetchone()
    return {
        "start": run[0][0].isoformat(sep=" "),
        "end": run[-1][0].isoformat(sep=" "),
        "days": (run[-1][0].date() - run[0][0].date()).days + 1,
        "files": len(run),
        "place": [p for p, _ in place.most_common(3)],
        "occasion": [o for o, _ in occasion.most_common(2)],
        "people": [p for p, _ in people.most_common(8)],
        "description": (desc[0] if desc else ""),
        "hashes": hs,
    }


def ask(a, db):
    import glob
    import numpy as np
    import urllib.request
    events = json.load(open(a.out, encoding="utf-8"))["events"]
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("GOOGLE_API_KEY is not set")
        return 1

    def emb(t):
        body = {"model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": t}]}, "outputDimensionality": 768}
        r = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-embedding-001:embedContent",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json", "x-goog-api-key": key},
            method="POST")
        with urllib.request.urlopen(r, timeout=90) as resp:
            v = np.array(json.loads(resp.read())["embedding"]["values"],
                         dtype=np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    # An event is searched by what it WAS: when, where, who, and one
    # description. Embedding every file again would answer the old question.
    texts = []
    for e in events:
        texts.append("{} {}. {} {}. {}".format(
            e["start"][:10], " ".join(e["place"]), " ".join(e["occasion"]),
            ", ".join(e["people"][:6]), e["description"][:300]))
    H = []
    for s in sorted(glob.glob(os.path.join(P.AUDIT, "event-vectors", "*.npz"))):
        with np.load(s, allow_pickle=False) as z:
            H.append(z["vec"])
    if H:
        V = np.concatenate(H).astype(np.float32)
    else:
        print("embedding {:,} events once...".format(len(texts)), flush=True)
        V = np.array([emb(t) for t in texts], dtype=np.float32)
        os.makedirs(os.path.join(P.AUDIT, "event-vectors"), exist_ok=True)
        tmp = os.path.join(P.AUDIT, "event-vectors", "events.tmp")
        with open(tmp, "wb") as fh:
            np.savez(fh, vec=V.astype(np.float16))
            fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, os.path.join(P.AUDIT, "event-vectors", "events.npz"))
    if len(V) != len(events):
        print("STOPPING: {:,} vectors for {:,} events - rebuild them "
              "(delete event-vectors/)".format(len(V), len(events)))
        return 1
    V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
    sims = V @ emb(a.ask)
    print('"{}"'.format(a.ask))
    print()
    for i in np.argsort(-sims)[:a.top]:
        e = events[i]
        print("  {:.3f}  {} to {}  ({} day(s), {:,} photographs)".format(
            float(sims[i]), e["start"][:10], e["end"][:10], e["days"], e["files"]))
        bits = []
        if e["place"]:
            bits.append("/".join(e["place"][:2]))
        if e["people"]:
            bits.append(", ".join(e["people"][:5]))
        if bits:
            print("         {}".format("  |  ".join(bits)))
        if e["description"]:
            print("         {}".format(e["description"][:100]))
    meta = json.load(open(a.out, encoding="utf-8"))
    print()
    print("  {:,} events from {:,} dated files. {:,} of {:,} files have no "
          "clock and are in NO event.".format(
              len(events), meta["dated_files"], meta["undated_files"],
              meta["total_files"]))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--gap", type=float, default=14.0,
                    help="hours of silence that end an event. 14 puts a whole "
                         "day together and separates it from the next one.")
    ap.add_argument("--min-files", type=int, default=4,
                    help="a run smaller than this is a moment, not an event")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ask", default="")
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()

    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")), uri=True)
    if a.ask:
        if not os.path.exists(a.out):
            print("no events yet - run with --apply first")
            return 2
        rc = ask(a, db)
        db.close()
        return rc

    rows, runs, kept, total = load(db, a.gap, a.min_files)
    print("dated files      : {:,} of {:,} ({:.1f}%)".format(
        len(rows), total, 100.0 * len(rows) / total))
    print("files with NO clock, in no event: {:,}".format(total - len(rows)))
    print("runs at a {:.0f}h gap : {:,}".format(a.gap, len(runs)))
    print("events of {}+ files: {:,}".format(a.min_files, len(kept)))
    print("  covering {:,} photographs".format(sum(len(r) for r in kept)))
    if kept:
        big = sorted(kept, key=len, reverse=True)[:5]
        print("\n  biggest:")
        for r in big:
            print("    {} to {}  {:,} files".format(
                r[0][0].date(), r[-1][0].date(), len(r)))
    if not a.apply:
        print("\nreport only. Re-run with --apply.")
        db.close()
        return 0

    events = [describe(db, r) for r in kept]
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"built": dt.datetime.now().isoformat(timespec="seconds"),
                   "gap_hours": a.gap, "min_files": a.min_files,
                   "total_files": total, "dated_files": len(rows),
                   "undated_files": total - len(rows),
                   "events": events}, fh, indent=1)
        fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, a.out)
    print("\nwrote {:,} events to {}".format(len(events), a.out))
    print('Ask it: build_events.py --ask "..."')
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
