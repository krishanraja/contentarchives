r"""Recount everything from disk and update the repo's state. One command.

The canon is only worth trusting if updating it is easier than not updating it.
Three steps in the right order:

    origin_map.py     rebuild the origin map from the ingest manifest
    track.py          recount library, ingest, losses, disks
    publish_state.py  redact, run the tripwire, write state/

Run it at the end of any session that moved, added or removed files - including a
session that ran out of time part-way. A half-finished ingest with an accurate
checkpoint is recoverable; one with a stale record is not.

    python tools/refresh.py
    python tools/refresh.py --check    # verify only, write nothing
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, args: list[str]) -> None:
    print(f"\n=== {script} " + "=" * (60 - len(script)))
    r = subprocess.run([sys.executable, str(HERE / script), *args])
    if r.returncode != 0:
        sys.exit(f"\n{script} failed (exit {r.returncode}). state/ not updated.")


def main() -> None:
    check = "--check" in sys.argv
    passthrough = [a for a in sys.argv[1:] if a != "--check"]

    if not check:
        run("origin_map.py", passthrough)
        run("track.py", [])
    run("publish_state.py", ["--dry-run"] if check else [])

    print()
    if check:
        print("Check passed. Nothing written.")
    else:
        print("state/ is current. Commit and push it:")
        print("    git add state/ && git commit -m 'Update state' && git push")


if __name__ == "__main__":
    main()
