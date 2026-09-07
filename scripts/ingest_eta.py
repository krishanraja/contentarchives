r"""Projected finish time for the archive ingest, measured rather than guessed.

Progress is weighted by BYTES, not by member count. Member count is the number
that is easy to read and the one that lies: a part whose members average 4 MB
and a part whose members average 12 MB advance the counter at the same rate and
the disk at three times the difference. Every ETA here is bytes done over bytes
total, with the rate taken from work actually observed.

Two rates are reported because they answer different questions:

  average       bytes done since this archive started, over elapsed time.
                Stable, and the right basis for "when will the queue drain".
  current       measured over a live sample window (--sample). Reacts to a
                video-heavy stretch that the average has not caught up with.

An archive that has not started yet is projected at the average rate, which is
the only evidence available for it. That projection is labelled, because a
number carried forward from other work is weaker evidence than a measurement,
and the difference should be visible rather than implied.

    python ingest_eta.py                 # project the whole queue
    python ingest_eta.py --sample 30     # also measure the current rate
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopilot as ap                                          # noqa: E402

AUDIT = r"D:\_PhotoAudit"
PROG = os.path.join(AUDIT, "arc-progress")
CACHE = os.path.join(AUDIT, "arc-sizes.json")
WATCH = [r"C:\Users\user\Downloads", "D:\\", r"C:\GoogleTakeout", r"D:\Takeout"]


def hms(seconds: float) -> str:
    if seconds < 0 or seconds != seconds or seconds == float("inf"):
        return "?"
    s = int(seconds)
    if s < 3600:
        return f"{s//60}m {s%60:02d}s"
    return f"{s//3600}h {(s%3600)//60:02d}m"


def load_cache() -> dict:
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {}


def member_sizes(path: str, cache: dict) -> dict[str, int]:
    """media member -> size, from the central directory. Cached by path+size."""
    st = os.stat(path)
    key = f"{os.path.basename(path)}|{st.st_size}"
    if key in cache:
        return cache[key]
    out = {}
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.is_dir():
                continue
            if os.path.splitext(i.filename)[1].lower() in ap.MEDIA:
                out[i.filename] = i.file_size
    cache[key] = out
    try:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    except Exception:
        pass
    return out


def handled(archive_name: str) -> set[str]:
    p = os.path.join(PROG, archive_name + ".csv")
    if not os.path.exists(p):
        return set()
    out = set()
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if row:
                out.add(row[0])
    return out


def archives() -> list[str]:
    found = []
    for d in WATCH:
        try:
            for fn in sorted(os.listdir(d)):
                low = fn.lower()
                if low.startswith("takeout") and low.endswith(".zip"):
                    found.append(os.path.join(d, fn))
        except OSError:
            pass
    return found


def done_units() -> set[str]:
    p = os.path.join(AUDIT, "autopilot-state.csv")
    s = set()
    if os.path.exists(p):
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r:
                    s.add(r[0])
    return s


def main() -> None:
    ap_ = argparse.ArgumentParser(description=__doc__)
    ap_.add_argument("--sample", type=int, default=0, metavar="SEC",
                     help="measure the current rate over this many seconds")
    a = ap_.parse_args()

    cache = load_cache()
    done = done_units()
    rows, active = [], None

    for path in archives():
        name = os.path.basename(path)
        if name in done:
            continue
        sizes = member_sizes(path, cache)
        total_b = sum(sizes.values())
        h = handled(name)
        done_b = sum(v for k, v in sizes.items() if k in h)
        started = None
        cp = os.path.join(PROG, name + ".csv")
        if os.path.exists(cp):
            started = os.path.getctime(cp)
        rows.append(dict(name=name, total_b=total_b, done_b=done_b,
                         members=len(sizes), done_m=len(h), started=started))
        if started and 0 < done_b < total_b:
            active = rows[-1]

    if not rows:
        print("no pending archives")
        return

    now = time.time()
    rate = None
    if active:
        elapsed = now - active["started"]
        if elapsed > 0 and active["done_b"] > 0:
            rate = active["done_b"] / elapsed

    cur_rate = None
    members_min = None
    if a.sample and active:
        # A short window can complete ZERO members - one 2 GB video takes longer
        # than the window - and reporting that as a stalled ingest is wrong. So
        # sample long enough to clear a large member, and say so explicitly when
        # nothing completed rather than printing nothing at all.
        b0 = active["done_b"]
        m0 = active["done_m"]
        t0 = time.time()
        print(f"sampling current rate for {a.sample}s...", flush=True)
        time.sleep(a.sample)
        sizes = member_sizes(os.path.join(
            [d for d in WATCH if os.path.exists(os.path.join(d, active["name"]))][0],
            active["name"]), cache)
        h = handled(active["name"])
        b1 = sum(v for k, v in sizes.items() if k in h)
        dt_ = time.time() - t0
        if dt_ > 0 and b1 > b0:
            cur_rate = (b1 - b0) / dt_
            members_min = (len(h) - m0) * 60.0 / dt_
            active["done_b"] = b1
            active["done_m"] = len(h)
        else:
            print(f"  no member completed in {a.sample}s - normal on a video-heavy "
                  f"part, where one member can exceed the window. Not a stall: "
                  f"check the checkpoint file's mtime to confirm work is landing.")

    GB = 1024 ** 3
    print()
    print(f"{'archive':<38} {'media':>7} {'done':>7} {'GB done':>9} {'GB left':>9}  eta")
    print("-" * 92)
    cum_left = 0.0
    proj = cur_rate or rate
    for r in rows:
        left_b = r["total_b"] - r["done_b"]
        cum_left += left_b
        if proj:
            eta_s = cum_left / proj
            when = dt.datetime.now() + dt.timedelta(seconds=eta_s)
            mark = "" if r is active else "  (projected at observed rate)"
            eta = f"{hms(eta_s):>9}  ~{when:%H:%M}{mark}"
        else:
            eta = "        ?  (not started - no rate yet)"
        print(f"{r['name']:<38} {r['members']:>7,} {r['done_m']:>7,} "
              f"{r['done_b']/GB:>9.1f} {left_b/GB:>9.1f}  {eta}")

    print("-" * 92)
    if rate:
        print(f"average rate : {rate/1024**2:6.1f} MB/s   ({rate/GB*60:.2f} GB/min)"
              f"   <- includes dead time, so PESSIMISTIC")
        print("               (each driver pass rebuilds the library index before it "
              "reads a byte,\n                and that idle time is inside this average)")
    if cur_rate:
        print(f"current rate : {cur_rate/1024**2:6.1f} MB/s   ({cur_rate/GB*60:.2f} GB/min)"
              + (f", {members_min:.0f} members/min" if members_min else "")
              + f"   [{a.sample}s sample]")
        print("               current is the honest basis for an ETA; average is a floor.")
    if proj:
        total_eta = cum_left / proj
        print(f"\nqueue drains in {hms(total_eta)} "
              f"-> ~{dt.datetime.now() + dt.timedelta(seconds=total_eta):%H:%M}"
              f"  ({cum_left/GB:.1f} GB of media left)")
        print("\nProjection for not-yet-started archives assumes the observed rate holds.")
        print("It will not if their members are markedly larger or smaller - re-run to recheck.")


if __name__ == "__main__":
    main()
