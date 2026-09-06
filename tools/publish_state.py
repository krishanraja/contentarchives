r"""Publish local state into the repo, redacted, so this repo is the canon.

The repo is public. The origin map is derived from real paths, and real paths
carry real names - family members, medical documents, immigration paperwork.
Those must not be committed verbatim.

But redacting them into nothing would defeat the point. The map exists so a
future session can plan a quarantine batch by *origin folder*, and it can only
do that if the folders stay distinguishable. So sensitive terms are replaced
with stable pseudonyms - `bharti` always becomes `PERSON-A`, everywhere, in both
outputs - and the key that reverses them stays on this machine only.

Two safeguards, because a redaction that silently misses something is worse than
no redaction at all:

  1. The key file lives outside the repo and is never committed.
  2. A tripwire scans the *redacted* output for anything that still looks
     sensitive. If it finds a hit, nothing is written and the run fails loudly.
     New sources will bring new names; the tripwire is what makes that a visible
     failure rather than a silent leak.

Only the folder-level view is published. The first tripwire run proved why: the
per-file map leaks through *filenames*, not just folders - scans of passports,
identity and spouse-visa paperwork name themselves. Redacting hundreds of those
individually would be a standing hazard, and the per-file map is regenerable
from the manifest with `origin_map.py` anyway, so it stays on the machine that
holds the library. `--include-file-map` publishes it, and is only appropriate if
this repo is private.

The tripwire also writes what it found to SENSITIVE-FILES.csv next to the audit
data - never into the repo. Those hits are exactly the documents worth pulling
out of a photo library, so the safety check doubles as the first pass of the
quarantine review.

    python tools/publish_state.py                 # redact, verify, write state/
    python tools/publish_state.py --dry-run       # check only, write nothing
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_DIR = REPO / "state"

DEFAULT_AUDIT = Path(r"D:\_PhotoAudit")
DEFAULT_KEY = DEFAULT_AUDIT / "redaction-key.json"

# Anything matching these in the redacted output stops the publish. Deliberately
# broad: a false alarm costs one line in the key file, a miss costs a leak.
TRIPWIRE = re.compile(
    r"\b("
    r"passport|visa|immigration|citizenship|oci"
    r"|discharge|medical|diagnos\w*|prescription|nhs|hospital|clinic"
    r"|birth\s*cert\w*|marriage\s*cert\w*|divorce|solicitor|probate"
    r"|payslip|salary|p60|p45|hmrc|tax\s*return|mortgage|bank\s*statement"
    r"|national\s*insurance|nino"
    r")\b",
    re.I,
)


def load_key(path: Path) -> dict[str, str]:
    if not path.exists():
        sys.exit(
            f"No redaction key at {path}.\n"
            "Create one - a JSON object mapping each sensitive literal to its\n"
            'stable pseudonym, e.g. {"somename": "PERSON-A"}. It stays local.'
        )
    key = json.loads(path.read_text(encoding="utf-8"))
    # Longest first, so a term that contains another is replaced whole.
    return dict(sorted(key.items(), key=lambda kv: -len(kv[0])))


def redact(text: str, key: dict[str, str]) -> str:
    for literal, replacement in key.items():
        text = re.sub(re.escape(literal), replacement, text, flags=re.I)
    return text


def scan(text: str, key: dict[str, str]) -> list[str]:
    """Tripwire hits in already-redacted text.

    The pseudonyms are masked out first. A replacement like `MEDICAL-DOC-1` is
    the redaction working, not a leak, and left unmasked it would make the
    tripwire fire on every row it successfully cleaned.
    """
    probe = text
    for replacement in set(key.values()):
        probe = probe.replace(replacement, "*")
    return [m.group(0) for m in TRIPWIRE.finditer(probe)]


def flag_sensitive_files(audit: Path, key: dict[str, str]) -> int:
    """Library files whose own name suggests an identity or financial document.

    Written beside the audit data, never into the repo. A photo library is the
    wrong home for a passport scan, so this is the shortlist to move out.
    """
    src = audit / "ORIGIN-MAP.csv"
    if not src.exists():
        return 0
    out = audit / "SENSITIVE-FILES.csv"
    n = 0
    with open(src, newline="", encoding="utf-8", errors="ignore") as f,             open(out, "w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["LibraryPath", "OriginPath", "MatchedTerms", "Bytes"])
        for row in csv.DictReader(f):
            name = Path(row.get("LibraryPath", "")).name
            terms = scan(name, key)
            if terms:
                w.writerow([row.get("LibraryPath", ""), row.get("OriginPath", ""),
                            ";".join(sorted(set(t.lower() for t in terms))),
                            row.get("Bytes", "")])
                n += 1
    print(f"flagged   {n:,} document-like files -> {out}")
    return n


def redact_csv(src: Path, dst: Path, key: dict[str, str],
               columns: list[str], gz: bool = False) -> list[str]:
    """Redact the named columns. Returns any tripwire hits found afterwards."""
    hits: list[str] = []
    rows_out = []
    with open(src, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        for row in reader:
            for c in columns:
                if c in row and row[c]:
                    row[c] = redact(row[c], key)
            joined = " ".join(row.get(c, "") for c in columns)
            for term in scan(joined, key):
                hits.append(f"{term}  in  {joined[:160]}")
            rows_out.append(row)

    if hits:
        return hits                       # write nothing when the tripwire fires

    opener = (lambda p: gzip.open(p, "wt", newline="", encoding="utf-8")) if gz \
        else (lambda p: open(p, "w", newline="", encoding="utf-8"))
    with opener(dst) as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-file-map", action="store_true",
                    help="also publish the per-file map. Private repos only.")
    a = ap.parse_args()

    key = load_key(a.key)
    STATE_DIR.mkdir(exist_ok=True)
    all_hits: list[str] = []

    jobs = [
        (a.audit / "ORIGIN-FOLDERS.csv", STATE_DIR / "origin-folders.csv",
         ["OriginFolder"], False),
    ]
    if a.include_file_map:
        jobs.append((a.audit / "ORIGIN-MAP.csv", STATE_DIR / "origin-map.csv.gz",
                     ["LibraryPath", "OriginPath", "OriginFolder"], True))

    flag_sensitive_files(a.audit, key)

    for src, dst, cols, gz in jobs:
        if not src.exists():
            print(f"skipped (not found): {src}")
            continue
        target = Path(str(dst) + ".check") if a.dry_run else dst
        hits = redact_csv(src, target, key, cols, gz)
        if a.dry_run and target.exists():
            target.unlink()
        if hits:
            all_hits += hits
            print(f"TRIPWIRE  {src.name}: {len(hits)} hit(s)")
        else:
            print(f"ok        {src.name} -> {dst.relative_to(REPO)}")

    # STATE.json / PROGRESS.md are generated figures and paths we already publish.
    for name in ("STATE.json", "PROGRESS.md"):
        src = a.audit / name
        if not src.exists():
            continue
        text = redact(src.read_text(encoding="utf-8", errors="ignore"), key)
        for term in scan(text, key):
            all_hits.append(f"{term}  in  {name}")
        if not a.dry_run and not all_hits:
            (STATE_DIR / name).write_text(text, encoding="utf-8")
            print(f"ok        {name} -> state/{name}")

    if all_hits:
        print()
        print("NOTHING WAS WRITTEN. The tripwire matched terms that the key does")
        print("not cover. Add them to the key file and run again:")
        print()
        for h in list(dict.fromkeys(all_hits))[:40]:
            print(f"  {h}")
        if len(set(all_hits)) > 40:
            print(f"  ... and {len(set(all_hits)) - 40} more distinct hit(s)")
        sys.exit(1)

    print()
    print("state/ is current." if not a.dry_run else "dry run clean.")


if __name__ == "__main__":
    main()
