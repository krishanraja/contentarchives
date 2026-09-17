r"""Write the explicit list of files a purge may destroy. Nothing else may.

    python build_purge_list.py --scope intimate-folder
    python build_purge_list.py --scope intimate-folder --out D:\_PhotoAudit\purge-targets.csv

WHY THE LIST IS A SEPARATE STEP

`purge_content.py` refuses to run without a reviewed CSV of `Hash,Path`, and
takes no globs, no folder roots and no path substrings. That is deliberate: a
path-substring rule on this project once destroyed 45 irreplaceable personal
files, and the only defence that has ever held is naming every victim
individually and re-hashing it at the instant of deletion.

So this builds the list, prints it for a human to read, and writes it. It
destroys nothing and it is safe to run repeatedly.

THE SCOPES, EXACTLY AS KRISH DREW THEM (2026-09-18)

  intimate-folder   the files whose sensitivity is `intimate` AND whose parent
                    directory is exactly `Media\Personal\Intimate`. This is
                    what he chose: 88 files. NOT the 2 classified intimate that
                    sit elsewhere - a doctored wedding photo and an animated
                    meme, on which the narrow nudity pass disagrees with the
                    broad one - and NOT the private-family hits, which are a
                    2019 back-wound series, hospital photographs and newborn
                    skin-to-skin shots.

  intimate-all      adds those 2. Offered because the sweep's "0 classified
                    intimate outside the folder" invariant reads 2 until they
                    are resolved one way or the other.

The query deliberately does NOT join files to v_files on hash: v_files is one
row per PATH, and that join multiplies duplicate paths against duplicate rows
(learning 56). A purge list built from a fan-out would name the same file twice.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401

import paths as P                                                 # noqa: E402

DEST = os.path.join(P.PERSONAL, "Intimate")
EXPECTED = {"intimate-folder": 88, "intimate-all": 90}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--scope", default="intimate-folder",
                    choices=sorted(EXPECTED))
    ap.add_argument("--out", default=os.path.join(P.AUDIT, "purge-targets.csv"))
    ap.add_argument("--expect", type=int, default=0,
                    help="refuse to write unless the scope yields exactly this "
                         "many files. Defaults to the count recorded for the "
                         "scope, so a silent change in the data stops the run.")
    a = ap.parse_args()

    db = sqlite3.connect("file:{}?mode=ro".format(
        a.db.replace("\\", "/")), uri=True)
    try:
        sens = {h: (s or "").strip() for h, s in db.execute(
            "select hash, max(coalesce(sensitivity,'')) from v_files "
            "group by hash")}
        kinds = {h: (k or "") for h, k in db.execute(
            "select hash, max(coalesce(kind,'')) from v_files group by hash")}
        rows = db.execute("select path, hash, bytes from files").fetchall()
    finally:
        db.close()

    picked = []
    for path, h, nbytes in rows:
        if not h or sens.get(h) != "intimate":
            continue
        inside = os.path.dirname((path or "").replace("/", "\\")).lower() \
            == DEST.lower()
        if a.scope == "intimate-folder" and not inside:
            continue
        picked.append((h, path, nbytes or 0, kinds.get(h) or "?"))

    picked.sort(key=lambda t: t[1].lower())
    print("scope     : {}".format(a.scope))
    print("files     : {}".format(len(picked)))
    print("bytes     : {:,}".format(sum(t[2] for t in picked)))
    print("by kind   : {}".format(dict(
        collections.Counter(t[3] for t in picked))))

    dupes = [h for h, n in collections.Counter(
        t[0] for t in picked).items() if n > 1]
    if dupes:
        print()
        print("STOPPING: {} hash(es) appear more than once - the list would "
              "name the same content twice.".format(len(dupes)))
        return 1

    # THE DISK DECIDES WHAT IS ON THE LIST, AND THE COUNT GUARD JUDGES THAT.
    #
    # This used to check --expect against the INDEX row count and only then look
    # at the filesystem. The index is a record that goes stale the moment a file
    # moves or is removed, so the guard compared an expectation about what would
    # be DESTROYED against a number that merely described a database. On
    # 2026-09-18 Krish deleted 7 of the 88 himself; the index still said 88, so
    # `--expect 81` - the true count of files that existed - was refused by a
    # guard reading a stale row count. A guard that fires on the wrong quantity
    # trains the reader to override it, which is worse than no guard (learning
    # 44).
    #
    # So: resolve against the disk FIRST, report what is absent, and let
    # --expect mean "this many files will actually be destroyed".
    absent = [(h, p, b, k) for h, p, b, k in picked
              if not os.path.exists(
                  p if p.startswith("\\\\?\\") else "\\\\?\\" + p)]
    if absent:
        print()
        print("=== {} listed path(s) are already gone ===".format(len(absent)))
        print("  The index still names them; the filesystem does not. They are")
        print("  EXCLUDED from the list - a purge cannot destroy what is not")
        print("  there, and pretending otherwise would fake the count.")
        for h, p, b, k in absent:
            print("   {:>10,}  {}".format(b, os.path.basename(p)))
        picked = [t for t in picked if t not in absent]
        # WRITE IT, do not merely mention it. Saying "written to the -absent
        # list" without writing one is the flag-without-the-behaviour mistake,
        # and here it would lose the only record of which hashes still need
        # blocking after a purge that cannot touch them.
        ap_out = os.path.splitext(a.out)[0] + "-absent.csv"
        tmp_ap = ap_out + ".tmp"
        with io.open(tmp_ap, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Hash", "Path", "Bytes", "Kind", "Note"])
            for h, p, b, k in absent:
                w.writerow([h, p, b, k, "already absent from disk when the "
                                        "list was built"])
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_ap, ap_out)
        print()
        print("  Their hashes are still worth blocking, since a re-import could")
        print("  restore them: {}".format(ap_out))

    want = a.expect or EXPECTED[a.scope]
    if len(picked) != want:
        print()
        print("STOPPING: {} file(s) are present and would be destroyed, but "
              "--expect says {}.".format(len(picked), want))
        print("  Read the difference before purging anything. Pass --expect {} "
              "only once you have.".format(len(picked)))
        return 1

    tmp = a.out + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Hash", "Path", "Bytes", "Kind"])
        for h, path, nbytes, kind in picked:
            w.writerow([h, path, nbytes, kind])
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, a.out)

    print()
    print("=== the first and last few, so the list is read and not assumed ===")
    for h, path, nbytes, kind in picked[:5]:
        print("  {:<11} {:>10,}  {}".format(kind, nbytes, path))
    print("  ...")
    for h, path, nbytes, kind in picked[-3:]:
        print("  {:<11} {:>10,}  {}".format(kind, nbytes, path))
    print()
    print("written: {}".format(a.out))
    print("Nothing has been destroyed. Review this file, then:")
    print("  python purge_content.py --list {}".format(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
