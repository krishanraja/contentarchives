r"""Regenerate the canon from disk, verify it, and push.

The last stage of any run. Deliberately fails loudly rather than pushing a state
file that does not match reality:

  origin_map    rebuild the per-file origin map from the ingest manifest
  track         recount library, ingest, losses, disks
  publish_state redact, run the privacy tripwire, write state/
  check_manifest every recorded file must still exist, or be journalled
  git           commit and push

If the manifest check finds an unexplained absence it stops before pushing. A
committed state that says everything is fine, when a file has silently left the
library, is worse than no state at all.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(r"C:\Users\user\dev\contentarchives")
PY = sys.executable


def run(cmd: list[str], cwd: Path, label: str, allow_fail: bool = False) -> int:
    print(f"\n--- {label} " + "-" * (58 - len(label)), flush=True)
    r = subprocess.run(cmd, cwd=str(cwd))
    if r.returncode != 0 and not allow_fail:
        sys.exit(f"{label} failed (exit {r.returncode}); nothing pushed")
    return r.returncode


def main() -> None:
    run([PY, str(REPO / "tools" / "origin_map.py")], REPO, "origin map")
    run([PY, str(REPO / "tools" / "track.py")], REPO, "track")
    run([PY, str(REPO / "tools" / "publish_state.py")], REPO, "publish state")

    rc = run([PY, str(REPO / "tools" / "check_manifest.py")], REPO,
             "manifest check", allow_fail=True)
    if rc != 0:
        sys.exit("manifest check found an unexplained absence - NOT pushing. "
                 "Investigate before committing a state that claims all is well.")

    status = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO),
                            capture_output=True, text=True).stdout.strip()
    if not status:
        print("\nnothing changed - nothing to push")
        return

    print("\n--- committing " + "-" * 48)
    subprocess.run(["git", "add", "-A"], cwd=str(REPO), check=True)
    msg = (
        "Update state after the overnight consolidation run\n"
        "\n"
        "Regenerated from disk by track.py and origin_map.py, with the manifest\n"
        "reconciled against the filesystem before committing.\n"
        "\n"
        "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_01AFV2SkbJQM4K9Hm2psVtxh\n"
    )
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=str(REPO), check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=str(REPO), check=True)
    print("pushed")


if __name__ == "__main__":
    main()
