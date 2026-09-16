r"""Record what the index files actually DO through a rebuild.

    python sample_rebuild.py            # samples until build_db exits
    python sample_rebuild.py --seconds 3

WHY THIS EXISTS RATHER THAN A THIRD GUESS

chain_rounds.ps1's -Progress has now been wrong twice:

  v1  counted committed rows in library.db.tmp. build_db inserts inside one long
      transaction, so a mode=ro reader saw nothing: `still at 0` on four of five
      checkpoints, two stall strikes, `progress 0 -> 0`.
  v2  summed the BYTES of library.db.tmp and its -wal, falling back to the live
      file when no tmp exists. Round 16's run opened at baseline 766,623,744 and
      checkpoint 1 read `still at 692,263,728` - LOWER than the baseline, so it
      took a stall strike. The supervisor treats any non-increase as a stall,
      and four strikes kills the work.

Both fixes were reasoned about and both were wrong, which is the argument for
measuring: sample every file involved through a whole rebuild, then choose a
signal that provably rises. Anything else is a third guess (learning 54).

WHAT TO LOOK FOR IN THE TRACE

  - does library.db.tmp grow monotonically, or truncate and regrow?
  - does the -wal file dominate, and when does it checkpoint?
  - is (tmp + wal) ever lower than the live file it replaces?
  - is there a signal that only ever increases - rows in a committed table, the
    sum of all three files, the count of pages written?

Run it in one window and the rebuild in another, or let the chain start the
rebuild and start this immediately after.
"""

import argparse
import csv
import io
import os
import time

LIVE = r"D:\_PhotoAudit\library.db"
OUT = r"D:\_PhotoAudit\rebuild-progress-trace.csv"
WATCH = [LIVE, LIVE + ".tmp", LIVE + ".tmp-wal", LIVE + ".tmp-shm",
         LIVE + "-wal", LIVE + "-shm"]


def sizes():
    out = {}
    for p in WATCH:
        try:
            out[p] = os.path.getsize(p)
        except OSError:
            out[p] = 0
    return out


def build_db_running():
    """Is a build_db.py process alive? Counted by CommandLine, not by name."""
    try:
        import subprocess
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*build_db.py*' } | "
             "Measure-Object).Count"],
            capture_output=True, text=True, timeout=30)
        return int((r.stdout or "0").strip() or 0) > 0
    except Exception:                                            # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--max-minutes", type=float, default=40.0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    t0 = time.time()
    deadline = t0 + a.max_minutes * 60
    rows = []
    print("sampling every {:.0f}s, writing {}".format(a.seconds, a.out))
    print("{:>7}  {:>14} {:>14} {:>14}  {:>14}".format(
        "t+s", "live", "tmp", "tmp-wal", "tmp+wal"))
    seen_running = False
    while time.time() < deadline:
        s = sizes()
        el = time.time() - t0
        tmp_total = s[LIVE + ".tmp"] + s[LIVE + ".tmp-wal"]
        rows.append({
            "t": round(el, 1),
            "live": s[LIVE],
            "tmp": s[LIVE + ".tmp"],
            "tmp_wal": s[LIVE + ".tmp-wal"],
            "tmp_shm": s[LIVE + ".tmp-shm"],
            "live_wal": s[LIVE + "-wal"],
            "tmp_plus_wal": tmp_total,
        })
        print("{:>7.0f}  {:>14,} {:>14,} {:>14,}  {:>14,}".format(
            el, s[LIVE], s[LIVE + ".tmp"], s[LIVE + ".tmp-wal"], tmp_total))

        running = build_db_running()
        if running:
            seen_running = True
        elif seen_running:
            print()
            print("build_db has exited - stopping")
            break
        time.sleep(a.seconds)

    with io.open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print()
    print("{} samples -> {}".format(len(rows), a.out))

    # The question the trace exists to answer.
    tmp_series = [r["tmp_plus_wal"] for r in rows if r["tmp_plus_wal"]]
    if tmp_series:
        falls = sum(1 for i in range(1, len(tmp_series))
                    if tmp_series[i] < tmp_series[i - 1])
        print("tmp+wal: {:,} -> {:,}, fell {} time(s) of {} samples".format(
            tmp_series[0], tmp_series[-1], falls, len(tmp_series)))
    allthree = [r["live"] + r["tmp"] + r["tmp_wal"] for r in rows]
    falls = sum(1 for i in range(1, len(allthree)) if allthree[i] < allthree[i - 1])
    print("live+tmp+wal: {:,} -> {:,}, fell {} time(s) of {} samples".format(
        allthree[0], allthree[-1], falls, len(allthree)))


if __name__ == "__main__":
    main()
