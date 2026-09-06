r"""Run the remaining work as one sequential pipeline, with live ETAs.

Built because waiting on jobs one at a time, and being asked "where is this at",
both waste the session. This runs the stages back to back, and every 60 seconds
writes a heartbeat carrying a recalculated estimate for the current stage and for
the run as a whole.

The estimate comes from the work itself, not from a guess. Each underlying script
already prints `N/M` progress lines; the runner parses those, measures the actual
rate over the last minute, and projects from it. Rates on this hardware vary by an
order of magnitude depending on whether a stage is hashing large video or walking
metadata, so a fixed estimate would be useless - it is recalculated continuously and
converges as the stage runs.

Stages run in sequence deliberately. D: corrupts data under parallel write load,
which is how three Takeout downloads ended up shrinking rather than growing.

    python runner.py            # run everything
    python runner.py --from 3   # resume at stage 3
    python runner.py --list
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time

PY = sys.executable
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
AUDIT = r"D:\_PhotoAudit"
STATUS = os.path.join(AUDIT, "RUN-STATUS.json")
LOG = os.path.join(AUDIT, "RUN-LOG.txt")

PROGRESS_RE = re.compile(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)")

STAGES = [
    ("inspect-old-zips",
     [PY, "-u", os.path.join(SCRIPTS, "inspect_old_zips.py")],
     "read the 2022/2024 export archives and flag media with no size match"),
    ("ingest-family-phone",
     [PY, "-u", os.path.join(SCRIPTS, "ingest_tree.py"),
      "--source", r"D:\2019-09-15 PERSON-A phone upto sept 2019",
      "--label", "family-phone-2019", "--min-size", "0", "--apply"],
     "76 files, 1.85 GB of family phone media not yet in the library"),
    ("purge-redundant",
     [PY, "-u", os.path.join(SCRIPTS, "purge_redundant.py"), "--apply"],
     "delete byte-identical copies across the laptop backups, keeping one"),
    ("refresh-canon",
     [PY, "-u", os.path.join(SCRIPTS, "refresh_and_push.py")],
     "regenerate origin map and state, verify the manifest, push to GitHub"),
]


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%H:%M:%S}  {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fmt(seconds: float) -> str:
    if seconds < 0 or seconds != seconds or seconds > 86400 * 7:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


class Stage:
    """Tracks one running stage and keeps a live estimate of its finish."""

    def __init__(self, name: str, index: int, total: int):
        self.name = name
        self.index = index
        self.total_stages = total
        self.done = 0
        self.total = 0
        self.started = time.time()
        self.samples: list[tuple[float, int]] = []
        self.lock = threading.Lock()

    def note(self, done: int, total: int) -> None:
        with self.lock:
            self.done, self.total = done, total
            now = time.time()
            self.samples.append((now, done))
            # keep a trailing window - early rates mislead badly once a stage
            # moves from small files to large ones
            self.samples = [s for s in self.samples if now - s[0] <= 180]

    def eta(self) -> float:
        with self.lock:
            if self.total <= 0 or len(self.samples) < 2:
                return -1
            (t0, d0), (t1, d1) = self.samples[0], self.samples[-1]
            if t1 <= t0 or d1 <= d0:
                return -1
            rate = (d1 - d0) / (t1 - t0)
            return (self.total - d1) / rate if rate > 0 else -1

    def pct(self) -> float:
        return (self.done / self.total * 100) if self.total else 0.0


def heartbeat(stage: Stage, stop: threading.Event, run_started: float) -> None:
    while not stop.wait(60):
        e = stage.eta()
        elapsed = time.time() - run_started
        msg = (f"STAGE {stage.index}/{stage.total_stages} {stage.name}  "
               f"{stage.done:,}/{stage.total:,} ({stage.pct():.0f}%)  "
               f"stage ETA {fmt(e)}  elapsed {fmt(elapsed)}")
        log(msg)
        try:
            with open(STATUS, "w", encoding="utf-8") as f:
                json.dump({"stage": stage.name, "index": stage.index,
                           "of": stage.total_stages, "done": stage.done,
                           "total": stage.total, "pct": round(stage.pct(), 1),
                           "stage_eta_seconds": round(e) if e > 0 else None,
                           "elapsed_seconds": round(elapsed),
                           "updated": dt.datetime.now().isoformat(timespec="seconds")},
                          f, indent=2)
        except OSError:
            pass


def run_stage(name: str, cmd: list[str], index: int, total: int,
              run_started: float) -> int:
    log(f"START {index}/{total} {name}")
    stage = Stage(name, index, total)
    stop = threading.Event()
    hb = threading.Thread(target=heartbeat, args=(stage, stop, run_started),
                          daemon=True)
    hb.start()

    out_path = os.path.join(AUDIT, f"stage-{index}-{name}.log")
    t0 = time.time()
    with open(out_path, "w", encoding="utf-8") as out:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1, errors="replace")
        for line in p.stdout:
            out.write(line)
            out.flush()
            m = PROGRESS_RE.search(line)
            if m:
                try:
                    stage.note(int(m.group(1).replace(",", "")),
                               int(m.group(2).replace(",", "")))
                except ValueError:
                    pass
        rc = p.wait()
    stop.set()
    log(f"{'DONE ' if rc == 0 else 'FAIL '} {index}/{total} {name}  "
        f"took {fmt(time.time() - t0)}  exit {rc}  -> {out_path}")
    return rc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for i, (n, _, d) in enumerate(STAGES, 1):
            print(f"  {i}. {n:<22} {d}")
        return

    run_started = time.time()
    log("=" * 70)
    log(f"RUN START  {len(STAGES)} stages, beginning at {a.start}")
    failures = []
    for i, (name, cmd, desc) in enumerate(STAGES, 1):
        if i < a.start:
            continue
        rc = run_stage(name, cmd, i, len(STAGES), run_started)
        if rc != 0:
            failures.append(name)
            log(f"  continuing past failure in {name}")
    log(f"RUN END  total {fmt(time.time() - run_started)}  "
        f"{'failures: ' + ', '.join(failures) if failures else 'all stages clean'}")


if __name__ == "__main__":
    main()
