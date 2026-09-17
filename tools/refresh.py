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
ROOT = HERE.parent


def run(script: str, args: list[str]) -> None:
    r"""Run one step. A name with a separator is REPO-relative; a bare name
    lives beside this file in tools/.

    This used to resolve everything against tools/. `master_sheet.py` moved to
    `stages/08_index/` in the 2026-09-15 stage migration and the call here kept
    its bare name, so `python tools/refresh.py --check` - the command RESUME.md
    tells every resuming session to run FIRST, before anything else - failed at
    exit 2 on a file-not-found and never reached the state/ update. The canon
    went stale for two days while the front door reported an error nobody read
    as fatal: state/PROGRESS.md said 73,821 files on 2026-09-16 while the index
    held 82,112.

    A missing step is fatal on purpose. A refresh that skips one publishes a
    state that looks complete and is not, which is worse than not refreshing.
    """
    target = (ROOT / script) if ("/" in script or "\\" in script) \
        else (HERE / script)
    print(f"\n=== {script} " + "=" * max(4, 60 - len(script)))
    if not target.exists():
        sys.exit(
            f"\nSTOPPING: {script} is not at {target}.\n"
            "  Fix the path rather than dropping the step: a refresh that\n"
            "  omits one publishes a state that reads as complete.")
    r = subprocess.run([sys.executable, str(target), *args])
    if r.returncode != 0:
        sys.exit(f"\n{script} failed (exit {r.returncode}). state/ not updated.")


def main() -> None:
    check = "--check" in sys.argv
    passthrough = [a for a in sys.argv[1:] if a != "--check"]

    if not check:
        run("origin_map.py", passthrough)
        run("track.py", [])
    run("publish_state.py", ["--dry-run"] if check else [])
    # The one sheet everything lands in. Regenerated last, because it
    # joins the library, the hash index, the inventory, the origin map
    # and the enrichment store - all of which are refreshed above.
    run("stages/08_index/master_sheet.py", [])

    print()
    if check:
        print("Check passed. Nothing written.")
    else:
        print("state/ is current. Commit and push it:")
        print("    git add state/ && git commit -m 'Update state' && git push")


if __name__ == "__main__":
    main()
