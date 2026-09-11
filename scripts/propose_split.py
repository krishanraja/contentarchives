r"""Propose the Personal / Communal split of the chronology, by origin folder.

Splitting by origin is the whole reason the origin map exists: 74,000 files reduce
to a few hundred folders, and a folder is something a person can actually judge.

This proposes, it does not act. Every origin folder is assigned a side and a reason,
and anything the evidence does not clearly settle is marked UNCLEAR rather than
guessed - because a wrong assignment here is invisible later, once the files have
moved.

  personal  the user's own devices, accounts and captures
  communal  family members' devices, shared albums, inherited archives
  unclear   needs a human

Writes SPLIT-PROPOSAL.csv for review.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict

ORIGIN = r"D:\_PhotoAudit\ORIGIN-MAP.csv"
OUT = r"D:\_PhotoAudit\SPLIT-PROPOSAL.csv"

# Family members' own devices and document sets. These are the clearest communal
# signal there is: a folder named for another person's phone.
COMMUNAL = re.compile(
    r"(PERSON-A|PERSON-B|PERSON-C|dadpics|mum|dad|nani|nana|grand|"
    r"family|shared|kunal|cousin)", re.I)

# The user's own devices and accounts.
PERSONAL = re.compile(
    r"(samsung s9|samsung s7|samsung s22|phone backup|samsung gallery|"
    r"samsung backup|dcim|camera|gopro|dji|whatsapp|surface|laptop|"
    r"onedrive|my drive|takeout|screenshots|pictures)", re.I)


def main() -> None:
    folders = defaultdict(lambda: {"n": 0, "bytes": 0, "root": "", "years": set()})
    with open(ORIGIN, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            lib = r["LibraryPath"]
            # only the chronology matters here
            if not (lib.startswith("Library") or lib.startswith("NoDate")):
                continue
            k = r["OriginFolder"]
            e = folders[k]
            e["n"] += 1
            e["bytes"] += int(r["Bytes"] or 0)
            e["root"] = r["SourceRoot"]
            e["years"].add(r["LibraryYear"])

    rows = []
    for fld, e in sorted(folders.items(), key=lambda kv: -kv[1]["bytes"]):
        c = bool(COMMUNAL.search(fld))
        p = bool(PERSONAL.search(fld))
        # Whose device or subject it is decides the side - not whose storage it
        # happened to sit in. A family member's phone backed up inside the
        # user's own Drive account is still that family member's phone, so the
        # communal signal outranks the personal one when both appear.
        if c:
            side = "communal"
            why = ("another person's device or archive"
                   + (", inside the user's own storage" if p else ""))
        elif p:
            side, why = "personal", "the user's own device, account or capture folder"
        else:
            side, why = "unclear", "no signal either way in the origin path"
        yrs = sorted(y for y in e["years"] if y not in ("?", ""))
        rows.append([side, fld, e["root"], e["n"], e["bytes"],
                     f"{yrs[0]}-{yrs[-1]}" if yrs else "?", why])

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Side", "OriginFolder", "SourceRoot", "Files", "Bytes",
                    "YearSpan", "Why"])
        w.writerows(rows)

    tot = defaultdict(lambda: [0, 0, 0])
    for side, _, _, n, b, _, _ in rows:
        tot[side][0] += 1
        tot[side][1] += n
        tot[side][2] += b

    print("PROPOSED SPLIT OF THE CHRONOLOGY")
    print("=" * 78)
    for side in ("personal", "communal", "unclear"):
        f_, n, b = tot[side]
        print(f"  {side:<10} {f_:>4} origin folders  {n:>7,} files  {b/1024**3:>7.2f} GB")
    print()

    for side in ("communal", "unclear"):
        sel = [r for r in rows if r[0] == side][:14]
        if not sel:
            continue
        print(f"{side.upper()} - largest origins")
        print("-" * 78)
        for s, fld, root, n, b, yrs, why in sel:
            print(f"  {n:>6,} {b/1024**3:>7.2f} GB  {yrs:<11} {fld[:44]}")
        print()

    print(f"written: {OUT}")
    print("\nNothing has moved. Review the CSV, correct any Side values, then apply.")


if __name__ == "__main__":
    main()
