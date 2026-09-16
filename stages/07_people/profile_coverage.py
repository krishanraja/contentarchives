r"""Every person Krish has named should be protected. Report, measure, add.

    python profile_coverage.py                 # report only
    python profile_coverage.py --apply         # add the safe ones

WHY THIS IS ONE SCRIPT AND NOT FIVE

Across rounds 13 to 15 this job was done by five throwaway files in a session
temp directory - measure_r13.py, measure_r15.py, add_r13_terms.py,
add_r14_stragglers.py, add_r15_terms.py - each a near-copy of the last. That is
exactly how check_repeats.py came to carry a stale `PEOPLE-round[1-6].html`
pattern for three rounds while reporting every sheet clean: copies drift, and a
tool you use every round should not live somewhere that is deleted.

WHAT IT PROTECTS

A profile term means THIS MATTERS: never swept, never compressed, never deleted,
overriding every exclusion rule (learning 1). The profile is SEEDED from these
same answers, so a name in the journal and not in the profile is a gap rather
than a decision. It held 27 of 222 for most of a day - Lily among them, 1,724
photographs, named in round 4 - because the original seeding dropped every name
under five characters and no later top-up revisited them.

HOW IT DECIDES

  - unprotected  = is_personal() says no. Asked through the REAL function on a
                   real-shaped path, never by comparing the name to the term
                   list, which was wrong three times in one afternoon: the
                   comparison runs the other way (learnings 54, instances 4-5).
  - safe to add  = the term matches under HALF the library. A name matching
                   almost everything would be a catch-all like "img" or "photo"
                   and would make the protection meaningless; nothing real has
                   come close - the widest measured is `old photos` at 6.03%.

Every added term is then asserted through is_personal() again, because the write
succeeding is not the same as the term working.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import shutil
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                                # noqa: E402
from guards.profile import load, path_of                         # noqa: E402

JOURNAL = os.path.join(r"D:\_enrichment", "answers.csv")
PROBE = r"D:\ContentLibrary\Media\Personal\2024\{} at dinner.jpg"
PAREN = re.compile(r"\s*\(.*?\)\s*")

# A term matching more than this share of the library is a catch-all, not a
# person. Deliberately loose: the widest real term is 6.03%, so this only ever
# fires on something like "img" or "dcim" (learning 54).
CATCH_ALL = 0.50

# The folder terms live at the end of personal_terms and stay there.
FOLDERS = ["bharti phone", "bhasker phone", "dadpics", "old photos",
           "core crew photos", "mick evans", "camera roll", "user photos"]


def named_people(journal):
    """Every person named in the answers journal, lowercased."""
    out = set()
    with io.open(journal, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("field") != "person" or not row.get("value"):
                continue
            v = PAREN.sub(" ", row["value"]).strip()
            if not v or v.lower().startswith(("for ", "unsure")):
                continue
            out.add(v.lower())
    return out


def library_paths(db_path):
    uri = "file:{}?mode=ro".format(db_path.replace("\\", "/"))
    db = None
    try:
        db = sqlite3.connect(uri, uri=True)
        return [r[0].lower() for r in db.execute("select path from files")]
    finally:
        if db is not None:
            db.close()


def add_terms(profile_path, terms):
    """Insert terms into safety.personal_terms, keeping the folder tail last."""
    backup = profile_path + ".bak-coverage"
    shutil.copy2(profile_path, backup)
    lines = io.open(profile_path, encoding="utf-8").read().splitlines()
    start = lines.index("  personal_terms:")
    end = start + 1
    while end < len(lines) and lines[end].startswith("    - "):
        end += 1
    items = [ln[len("    - "):] for ln in lines[start + 1:end]]
    if items[-len(FOLDERS):] != FOLDERS:
        raise SystemExit(
            "REFUSING: the folder tail is not where I expected it in {}.\n"
            "  Rewriting the term list blind could drop a protective term."
            .format(profile_path))
    names = items[:-len(FOLDERS)]
    added = [t for t in terms if t not in names]
    names = sorted(set(names) | set(added))
    lines[start + 1:end] = ["    - " + t for t in names + FOLDERS]
    io.open(profile_path, "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines) + "\n")
    return added, backup, len(names) + len(FOLDERS)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=JOURNAL)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--apply", action="store_true",
                    help="add the safe terms (default: report only)")
    a = ap.parse_args()

    if not os.path.isfile(a.journal):
        print("STOPPING: no answers journal at {}".format(a.journal))
        print("  A missing journal and an empty one look identical to a check")
        print("  that only asks whether the file exists, and the difference is")
        print("  whether every named person silently reads as protected.")
        return 1

    prof = load()
    print(prof)
    people = named_people(a.journal)
    print("people named in the journal : {}".format(len(people)))

    unprotected = sorted(n for n in people if not prof.is_personal(PROBE.format(n)))
    print("NOT protected by the profile: {}".format(len(unprotected)))
    if not unprotected:
        print()
        print("every named person is protected.")
        return 0

    paths = library_paths(a.db)
    total = len(paths)
    print("library paths               : {:,}".format(total))
    print()
    print("{:<22} {:>9} {:>8}  {}".format("term", "paths", "%", "verdict"))
    safe, refused = [], []
    for n in unprotected:
        hits = sum(1 for p in paths if n in p)
        pct = hits / max(total, 1)
        ok = pct < CATCH_ALL
        (safe if ok else refused).append(n)
        print("{:<22} {:>9,} {:>7.2f}%  {}".format(
            n, hits, pct * 100, "add" if ok else "CATCH-ALL - refused"))
    print()

    if not a.apply:
        print("report only. {} would be added; re-run with --apply.".format(len(safe)))
        return 0

    added, backup, now = add_terms(path_of(), safe)
    print("backed up to {}".format(backup))
    print("added {}: {}".format(len(added), ", ".join(added)))
    print("terms now: {}".format(now))

    # The write succeeding is not the term working.
    fresh = load()
    still = [t for t in safe if not fresh.is_personal(PROBE.format(t))]
    print()
    for t in safe:
        print("   {:<22} {}".format(
            t, "protected" if fresh.is_personal(PROBE.format(t)) else "NOT PROTECTED"))
    print()
    if still:
        print("STILL UNPROTECTED after adding: {}".format(still))
        return 1
    print("every added term is protected.")
    if refused:
        print("refused as catch-alls, unprotected on purpose: {}".format(refused))
    return 0


if __name__ == "__main__":
    sys.exit(main())
