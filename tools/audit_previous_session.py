r"""Verify what the previous session actually did, before building on it.

A session reports its own work, at the time, while inclined to see it as finished.
That is the worst possible vantage point from which to confirm anything. This checks
the claims against the filesystem instead.

It is deliberately blunt: every check either passes against something observable or
it fails. There is no "probably fine". A claim that cannot be verified is reported
as unverified, not assumed.

Run it first thing when resuming. Exit code is 1 if anything failed, so it can gate
further work.

    python tools/audit_previous_session.py
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

LIB = Path(r"D:\PhotoLibrary")
AUDIT = Path(r"D:\_PhotoAudit")
REPO = Path(__file__).resolve().parent.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


# --- 1. the canon matches the disk ------------------------------------------
try:
    state = json.loads((REPO / "state" / "STATE.json").read_text(encoding="utf-8"))
    claimed = state["library"]["total_files"]
    actual = 0
    for sub in ("Library", "NoDate"):
        for dp, _, fns in os.walk(LIB / sub):
            actual += len(fns)
    drift = abs(actual - claimed)
    check("state/STATE.json matches the library on disk",
          drift <= max(50, claimed * 0.001),
          f"claimed {claimed:,}, counted {actual:,}, drift {drift:,}")
except Exception as e:
    check("state/STATE.json readable", False, str(e))

# --- 2. every recorded file still exists ------------------------------------
r = subprocess.run([sys.executable, str(REPO / "tools" / "check_manifest.py"),
                    "--quiet"], capture_output=True)
check("manifest reconciles - no unexplained absences", r.returncode == 0,
      "check_manifest.py exit " + str(r.returncode))

# --- 3. deletions were journalled -------------------------------------------
journal = AUDIT / "user-directed-deletions.csv"
if journal.exists():
    with open(journal, newline="", encoding="utf-8", errors="ignore") as f:
        rows = list(csv.DictReader(f))
    unevidenced = [r for r in rows if not (r.get("Evidence") or "").strip()]
    check("every journalled deletion carries evidence", not unevidenced,
          f"{len(rows):,} deletions, {len(unevidenced)} without evidence")
else:
    check("deletion journal exists", False, "no user-directed-deletions.csv")

# --- 4. nothing is still running --------------------------------------------
try:
    out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
    busy = [n for n in ("python.exe", "robocopy.exe", "ffmpeg.exe") if n in out]
    check("no jobs left running from the previous session", not busy,
          f"running: {', '.join(busy)}" if busy else "clean")
except Exception as e:
    check("process check", False, str(e))

# --- 5. the structural work: claimed in docs, or actually on disk? ----------
# These are the checks that catch a plan being *written* rather than *applied*.
archive = Path(r"D:\Archive")
check("Archive schema exists on disk", archive.is_dir(),
      "D:\\Archive present" if archive.is_dir() else
      "D:\\Archive DOES NOT EXIST - the schema is documented but not applied")

split = (LIB / "Personal").is_dir() and (LIB / "Communal").is_dir()
check("chronology split into Personal/Communal", split,
      "both present" if split else
      "still a single Library/ tree - the split is agreed but not applied")

review = (LIB / "_Review").is_dir()
check("screenshot review bucket exists", review,
      "present" if review else "no _Review/ - classification has not run")

sensitive = AUDIT / "SENSITIVE-FILES.csv"
if sensitive.exists():
    with open(sensitive, newline="", encoding="utf-8", errors="ignore") as f:
        still = [r for r in csv.DictReader(f)
                 if os.path.exists(lp(str(LIB / r["LibraryPath"])))]
    check("identity documents moved out of the chronology", not still,
          f"{len(still)} still in the library" if still else "none remain")

# --- 6. scratch that should not survive -------------------------------------
scratch = [p for p in (r"D:\_zip_extract", r"D:\_lorimer_tmp", r"D:\_takeout_tmp",
                       r"D:\_compress_tmp") if Path(p).is_dir()]
check("no leftover scratch directories", not scratch,
      f"present: {', '.join(scratch)}" if scratch else "clean")


def main() -> None:
    print("AUDIT OF THE PREVIOUS SESSION")
    print("=" * 74)
    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{mark}] {name}")
        print(f"         {detail}")
    print("=" * 74)
    if failed:
        print(f"  {failed} of {len(results)} checks failed.")
        print()
        print("  A FAIL is not necessarily a mistake - work that was planned but")
        print("  deliberately deferred fails these too. What it means is: do not")
        print("  treat that item as done, and do not build on it until you have")
        print("  looked. Report each failure to the user before continuing.")
    else:
        print(f"  all {len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
