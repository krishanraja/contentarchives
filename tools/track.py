r"""Derive project state from artefacts on disk. Never from memory or narration.

Every number here is counted from a file that exists, not asserted. Run it any
time; it overwrites STATE.json and PROGRESS.md with whatever is actually true now.

    python track.py            # write state
    python track.py --print    # write state and show it
"""

from __future__ import annotations

import csv
import json
import os
import sys
import datetime as dt
from collections import Counter
from pathlib import Path

AUDIT = Path(r"D:\_PhotoAudit")
LIB = Path(r"D:\PhotoLibrary")
STATE = AUDIT / "STATE.json"
PROGRESS = AUDIT / "PROGRESS.md"
FINDINGS = AUDIT / "FINDINGS.md"          # append-only; fed into the repo later


def _count_lines(p: Path) -> int:
    if not p.exists():
        return 0
    with open(p, newline="", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def _walk_count(root: Path) -> tuple[int, int]:
    n = b = 0
    for dp, _, fns in os.walk(root):
        for fn in fns:
            try:
                b += os.path.getsize(os.path.join(dp, fn))
                n += 1
            except OSError:
                pass
    return n, b


def _free(drive: str) -> float:
    try:
        import shutil
        return shutil.disk_usage(drive).free / 1024 ** 3
    except OSError:
        return -1.0


def collect() -> dict:
    now = dt.datetime.now().isoformat(timespec="seconds")

    # The chronology is split into Personal/ and Communal/; Library/ now holds
    # only origins not yet assigned a side. Counting the pre-split paths alone
    # made STATE.json report 1,274 files for a 73,000-file library - and the
    # audit passed it, because it compared that figure against a count made the
    # same wrong way. Count every chronology root.
    sides = {name: _walk_count(LIB / name)
             for name in ("Personal", "Communal", "Library", "NoDate")}

    nod_n = nod_b = 0
    for base in (LIB, LIB / "Personal", LIB / "Communal"):
        n, b = _walk_count(base / "NoDate")
        nod_n += n
        nod_b += b

    total_n = sum(n for n, _ in sides.values())
    total_b = sum(b for _, b in sides.values())
    lib_n, lib_b = total_n - nod_n, total_b - nod_b

    # archives: what has been fully consumed, per the autopilot's own state file
    consumed = []
    st = AUDIT / "autopilot-state.csv"
    if st.exists():
        with open(st, newline="", encoding="utf-8") as f:
            consumed = [r[0] for r in csv.reader(f) if r]

    # archives still on disk anywhere we look
    pending = []
    for d in (Path("D:/"), Path("D:/Takeout"), Path("C:/GoogleTakeout"),
              Path(r"C:\Users\krish\Downloads")):
        try:
            for fn in os.listdir(d):
                low = fn.lower()
                if low.startswith("takeout") and low.endswith((".zip", ".tgz")):
                    pending.append(str(d / fn))
                elif low.endswith(".crdownload"):
                    pending.append(str(d / fn) + "  (downloading)")
        except OSError:
            pass

    # compression journal - verdicts are recorded per file
    verdicts = Counter()
    freed = 0
    jr = AUDIT / "compress-journal.csv"
    if jr.exists():
        with open(jr, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                verdicts[r.get("Verdict", "?")] += 1
                if r.get("Verdict") == "REPLACED":
                    try:
                        freed += int(r["BeforeBytes"]) - int(r["AfterBytes"])
                    except (ValueError, KeyError):
                        pass

    # per-archive ingestion progress
    arc_progress = {}
    apd = AUDIT / "arc-progress"
    if apd.exists():
        for f in apd.glob("*.csv"):
            arc_progress[f.stem] = _count_lines(f)

    return {
        "generated": now,
        "library": {
            "dated_files": lib_n,
            "dated_bytes": lib_b,
            "nodate_files": nod_n,
            "nodate_bytes": nod_b,
            "total_files": lib_n + nod_n,
            "chronology": {k.lower(): {"files": v[0], "bytes": v[1]}
                           for k, v in sides.items()},
        },
        "ingest": {
            "files_added_total": _count_lines(AUDIT / "autopilot-added.csv"),
            "duplicates_rejected": _count_lines(AUDIT / "autopilot-duplicates.csv"),
            "units_consumed": consumed,
            "archives_pending": pending,
            "archive_member_progress": arc_progress,
        },
        "rescue": {
            "e_drive_files_rescued": _count_lines(AUDIT / "e-rescue.csv"),
        },
        "compression": {
            "verdicts": dict(verdicts),
            "bytes_freed": freed,
            "candidates_planned": max(0, _count_lines(AUDIT / "big-files.csv") - 1),
        },
        "losses": {
            "unrecoverable_files": max(0, _count_lines(AUDIT / "FULL-loss-audit.csv") - 1),
            "personal_unrecoverable": max(0, _count_lines(AUDIT / "PERSONAL-losses.csv") - 1),
            "detail": "PERSONAL-losses.csv",
        },
        "disks_free_gb": {d: round(_free(d + ":\\"), 1) for d in ("C", "D", "G", "H")},
    }


def write_progress(s: dict) -> None:
    L, I, C = s["library"], s["ingest"], s["compression"]
    lines = [
        "# Consolidation progress",
        "",
        f"_Generated {s['generated']} by `track.py`. Every figure is counted from a",
        "file on disk, not asserted from memory._",
        "",
        "## Library",
        "",
        "| | files | GB |",
        "|---|---|---|",
        f"| Dated (`Library/YYYY/YYYY-MM`) | {L['dated_files']:,} | {L['dated_bytes']/1024**3:.1f} |",
        f"| Undated (`NoDate/`) | {L['nodate_files']:,} | {L['nodate_bytes']/1024**3:.1f} |",
        f"| **Total** | **{L['total_files']:,}** | **{(L['dated_bytes']+L['nodate_bytes'])/1024**3:.1f}** |",
        "",
        "## Ingestion",
        "",
        f"- files added: **{I['files_added_total']:,}**",
        f"- duplicates rejected on content hash: **{I['duplicates_rejected']:,}**",
        f"- E: drive files rescued: **{s['rescue']['e_drive_files_rescued']:,}**",
        f"- units fully consumed: {len(I['units_consumed'])}",
    ]
    for u in I["units_consumed"]:
        lines.append(f"  - `{u}`")
    if I["archives_pending"]:
        lines.append("- still to process:")
        for p in I["archives_pending"]:
            lines.append(f"  - `{p}`")
    if I["archive_member_progress"]:
        lines += ["", "| archive | members handled |", "|---|---|"]
        for k, v in sorted(I["archive_member_progress"].items()):
            lines.append(f"| `{k}` | {v:,} |")

    lines += ["", "## Compression", ""]
    if C["verdicts"]:
        lines += ["| verdict | files |", "|---|---|"]
        for k, v in sorted(C["verdicts"].items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v:,} |")
        lines.append("")
        lines.append(f"Space reclaimed: **{C['bytes_freed']/1024**3:.2f} GB** "
                     f"of {C['candidates_planned']:,} planned candidates.")
    else:
        lines.append(f"Not yet started. {C['candidates_planned']:,} candidates planned.")

    lines += [
        "",
        "## Losses",
        "",
        f"- files deleted with no surviving copy: **{s['losses']['unrecoverable_files']:,}**",
        f"- of those, personal/camera-original: **{s['losses']['personal_unrecoverable']:,}**",
        f"- itemised in `{s['losses']['detail']}`",
        "",
        "## Disks (GB free)",
        "",
        "| " + " | ".join(s["disks_free_gb"]) + " |",
        "|" + "---|" * len(s["disks_free_gb"]),
        "| " + " | ".join(str(v) for v in s["disks_free_gb"].values()) + " |",
        "",
    ]
    PROGRESS.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    s = collect()
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    write_progress(s)
    if not FINDINGS.exists():
        FINDINGS.write_text(
            "# Findings log\n\n"
            "Append-only. Each entry is a fact established from data, with how it was\n"
            "established. Folded into contentarchives/docs/LEARNINGS.md when confirmed.\n\n",
            encoding="utf-8")
    print(f"wrote {STATE}")
    print(f"wrote {PROGRESS}")
    if "--print" in sys.argv:
        print()
        print(PROGRESS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
