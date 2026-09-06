r"""Extract the media in old export archives that is not yet in the library.

Stage 1 read 25 archives and found 1,072 media members whose size matches nothing
in the library. Size is only a filter - it makes hashing cheap by ruling out the
95% that obviously match. This extracts the survivors and settles each one by
content.

Routing follows the agreed rubric rather than guessing:

  personal media   -> the library, deduped and dated like any other source
  work recordings  -> D:\_Staging\from-old-zips\work\, grouped by archive

Internal meeting recordings are work material: not memories, and not authored
output either. They are moved somewhere visible for a person to decide on, never
deleted by a script.

Streams each member rather than reading it whole - a 891 MB video read with
zipfile.read() is what gets a process killed on this machine (LEARNINGS rule 9).
"""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections import defaultdict

SRC = r"D:\_PhotoAudit\OLD-ZIP-CONTENTS.csv"
TMP = r"D:\_zip_extract"
WORK_OUT = r"D:\_Staging\from-old-zips\work"
REPORT = r"D:\_PhotoAudit\ZIP-EXTRACT.csv"
SCRIPTS = os.path.dirname(os.path.abspath(__file__))

# Paths inside an archive that mean "this is work, not a memory". Three kinds:
# internal meetings, employer-branded material, and anything rendered out of a
# deck - a video whose name still carries ".pptx" was a slide export.
WORK_RE = re.compile(
    r"(Meet Recordings|Meeting|Kick.?Off|Goal Setting|Business Update|Q&A"
    r"|Dashboard|Showcase|Weekly|Standup|Stand.?up|Retro|Webinar|Training"
    r"|101 |Intro with|Run through|Session"
    r"|EMPLOYER-A|EMPLOYER-A-PRODUCT|EMPLOYER-B|EMPLOYER-C"
    r"|Homepage|Header Video|Wordmark|[_ -]Logo[_ .]|Sizzle|Showreel"
    r"|\.pptx|\.ppt[_ .]|Presentation|Case Study|Webpage)", re.I)


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def safe_name(member: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", os.path.basename(member))[:120]


def extract_member(archive: str, member: str, dest: str) -> bool:
    """Stream one member out. Never loads it whole."""
    os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
    try:
        if archive.lower().endswith(".zip"):
            with zipfile.ZipFile(lp(archive)) as z, z.open(member) as src, \
                    open(lp(dest), "wb") as out:
                shutil.copyfileobj(src, out, 4 * 1024 * 1024)
        else:
            with tarfile.open(lp(archive), "r:*") as t:
                f = t.extractfile(member)
                if f is None:
                    return False
                with open(lp(dest), "wb") as out:
                    shutil.copyfileobj(f, out, 4 * 1024 * 1024)
        return True
    except (OSError, KeyError, zipfile.BadZipFile, tarfile.TarError) as e:
        print(f"  FAILED {os.path.basename(archive)}!{member[:50]}: {e}")
        return False


def main() -> None:
    apply = "--apply" in sys.argv

    rows = []
    with open(SRC, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            if r["SizeCheck"] == "no-size-match":
                rows.append((int(r["Bytes"]), r["Archive"], r["Member"]))
    rows.sort(reverse=True)

    personal = [r for r in rows if not WORK_RE.search(r[2])]
    work = [r for r in rows if WORK_RE.search(r[2])]

    print(f"{len(rows):,} members with no size match, "
          f"{sum(r[0] for r in rows)/1024**3:.2f} GB")
    print(f"  personal : {len(personal):>5,}  "
          f"{sum(r[0] for r in personal)/1024**3:>6.2f} GB  -> library")
    print(f"  work     : {len(work):>5,}  "
          f"{sum(r[0] for r in work)/1024**3:>6.2f} GB  -> {WORK_OUT}")
    print()
    print("LARGEST PERSONAL")
    for b, a, m in personal[:15]:
        print(f"  {b/1024**2:>8.1f} MB  {os.path.basename(m)[:56]}")

    if not apply:
        print("\nReport only. Re-run with --apply.")
        return

    os.makedirs(lp(TMP), exist_ok=True)
    out_rows = []
    n_ok = 0

    for i, (size, archive, member) in enumerate(rows, 1):
        if i % 25 == 0:
            print(f"  {i:,}/{len(rows):,} extracted", flush=True)
        is_work = bool(WORK_RE.search(member))
        arc_tag = re.sub(r"[^A-Za-z0-9]+", "_", os.path.basename(archive))[:40]
        if is_work:
            dest = os.path.join(WORK_OUT, arc_tag, safe_name(member))
        else:
            dest = os.path.join(TMP, arc_tag, safe_name(member))
        stem, ext = os.path.splitext(dest)
        k = 0
        while os.path.exists(lp(dest)):
            k += 1
            dest = f"{stem}__{k}{ext}"
        if extract_member(archive, member, dest):
            n_ok += 1
            out_rows.append(["work" if is_work else "personal", archive, member,
                             dest, size])

    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Route", "Archive", "Member", "Extracted", "Bytes"])
        w.writerows(out_rows)

    print(f"\nextracted {n_ok:,}/{len(rows):,}")
    print(f"report: {REPORT}")

    # Hand the personal side to the normal ingest, which settles duplicates on
    # content and dates from filename/EXIF. Size got them here; hash decides.
    if any(r[0] == "personal" for r in out_rows):
        print("\n--- ingesting the personal side ---", flush=True)
        subprocess.run([sys.executable, "-u",
                        os.path.join(SCRIPTS, "ingest_tree.py"),
                        "--source", TMP, "--label", "old-zips",
                        "--min-size", "0", "--apply"])
        print("\nNOTE: anything the ingest rejected as a duplicate is still in "
              f"{TMP} and can be deleted. Anything it placed is now hardlinked "
              "into the library.")


if __name__ == "__main__":
    main()
