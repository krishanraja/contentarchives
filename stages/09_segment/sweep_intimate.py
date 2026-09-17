r"""Move every file classified `intimate` into Media\Personal\Intimate. Journalled.

    python sweep_intimate.py                 # dry run: the plan, and nothing else
    python sweep_intimate.py --apply
    python sweep_intimate.py --verify        # re-derive the count from disk
    python sweep_intimate.py --reverse <journal>   # put every file back

Krish, 2026-09-18: *"move everything intimate in to a separate folder called
Intimate inside Personal, and ensure 0 intimate photos remain in any other
folder"*.

ONE FLAT FOLDER, NO YEARS

Krish, 2026-09-18: *"lets remove the chronology folder structure from Intimate
and just have all the media in that one folder"*. A `YYYY\` tree is right for a
life browsed by date and wrong for a drawer whose purpose is that nobody browses
it - 88 files spread over 14 year folders holding 1 to 24 files each were 14
places to look instead of one.

The flatten is not a separate mode. `plan()` treats a file as home only when it
sits DIRECTLY in the folder, so a file in `Intimate\2021\` is planned like any
other move: journal first, collision refusal, `--reverse` puts the year folders
back. Emptied subfolders are pruned after a successful sweep, because an empty
`Intimate\2021\` is still the structure he asked to remove.

That also promotes the collision guard from theoretical to load-bearing: two
photographs can share a basename across two years, and with flat destinations
they now aim at the same path. It stops the run, as it always did.

WHAT "0 REMAINING" CAN AND CANNOT MEAN

`sensitivity` is a VISION MODEL's judgement. After this runs, **0 files
CLASSIFIED intimate sit outside `Media\Personal\Intimate`**, and `--verify`
proves that against the filesystem. Whether the model caught every intimate
photograph is a different claim: 3,124 files have no `sensitivity` recorded at
all and 745 are `private-family`. This does not answer that, and must not be
read as if it did.

TWO OVERRIDES OF HIS, TAKEN KNOWINGLY

- 31 of the 88 sit in `_Review`, which stage 09 says is *"emptied by Krish,
  never by a rule"*. He was shown that and chose to move them anyway: his
  instruction was "0 intimate remain in ANY other folder", and `_Review` is
  another folder.
- 24 of the 88 are screenshots, memes or graphics rather than photographs of
  anybody. They move too. An Intimate folder holding a meme is untidy; an
  intimate photograph left in the chronology is the failure that matters.

WHY IT IS BUILT LIKE THE INDEX PROMOTE

Small on purpose - 88 files - because the same machinery has to carry the
18,985-file split move, and stage 09 has no tests at all. So: the journal is
written BEFORE anything moves, a destination that already exists stops the run
rather than being overwritten, and `--reverse` reads the journal back. A move
without a reversal is not a move, it is a hope.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import io
import os
import shutil
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402

DEST = os.path.join(P.PERSONAL, "Intimate")
FIELDS = ["when", "hash", "sensitivity", "kind", "source", "destination"]


def lp(p: str) -> str:
    r"""\\?\ prefix: these paths run past 260 characters."""
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def plan(db_path: str, dest: str) -> list:
    db = sqlite3.connect("file:{}?mode=ro".format(db_path.replace("\\", "/")),
                         uri=True)
    try:
        # NOT `files f LEFT JOIN v_files v ON v.hash = f.hash` (learning 56).
        # v_files is one row per PATH, so that join matches every path against
        # every other path sharing its hash: a duplicated intimate photograph
        # would appear in the plan twice, the collision guard would not fire
        # (same source, not a different one), and the move loop would try to
        # move a file its own earlier pass had already moved. Two queries, one
        # row per hash and one row per path, cannot fan out.
        sens = {}
        for h, s, k in db.execute(
                "select hash, max(coalesce(sensitivity,'')), "
                "max(coalesce(kind,'')) from v_files group by hash"):
            sens[h] = ((s or "").strip(), k or "")
        rows = [(p, h, sens[h][0], sens[h][1], y)
                for p, h, y in db.execute("select path, hash, year from files")
                if h in sens and sens[h][0] == "intimate"]
    finally:
        db.close()
    out = []
    for path, h, sens, kind, _year in rows:
        p = path.replace("/", "\\")
        # HOME IS THE FOLDER ITSELF, NOT THE TREE BENEATH IT.
        #
        # This one comparison is what makes the flatten an ordinary sweep. The
        # old test was `startswith(dest + "\\")`, which counts
        # `Intimate\2021\x.jpg` as already home - so after the destination went
        # flat, plan() would have found 0 files to move and reported success
        # over a folder still full of year subfolders.
        #
        # `year` is still selected because verify() shares this query; it is no
        # longer part of any destination.
        if os.path.dirname(p).lower() == dest.lower():
            continue                      # already home
        out.append({"when": dt.datetime.now().isoformat(timespec="seconds"),
                    "hash": h or "", "sensitivity": sens or "",
                    "kind": kind or "", "source": path,
                    "destination": os.path.join(dest, os.path.basename(p))})
    return out


def verify(db_path: str, dest: str) -> int:
    """Re-derive from the FILESYSTEM, not from the plan. Returns files outside."""
    rows = plan(db_path, dest)
    outside = [r for r in rows if os.path.exists(lp(r["source"]))]
    print("classified intimate, still outside {}: {}".format(dest, len(outside)))
    for r in outside[:10]:
        print("   {}".format(r["source"]))
    if not outside:
        print("0 files classified intimate remain in any other folder.")
        print("(Files with no sensitivity recorded are UNKNOWN, not clear:")
        print(" this says nothing about them.)")
    return len(outside)


def reverse(journal: str) -> int:
    rows = list(csv.DictReader(io.open(journal, encoding="utf-8", newline="")))
    print("reversing {:,} moves from {}".format(len(rows), journal))
    back = 0
    for r in rows:
        src, dst = r["source"], r["destination"]
        if not os.path.exists(lp(dst)):
            print("   missing, skipped: {}".format(dst))
            continue
        if os.path.exists(lp(src)):
            print("   REFUSING: {} is occupied again".format(src))
            continue
        os.makedirs(os.path.dirname(lp(src)), exist_ok=True)
        shutil.move(lp(dst), lp(src))
        back += 1
    print("put back: {:,} of {:,}".format(back, len(rows)))
    return 0 if back == len(rows) else 1


def prune_empty(dest: str) -> list:
    r"""Remove subfolders of `dest` left empty by the sweep, deepest first.

    An empty `Intimate\2021\` is still the chronology Krish asked to remove, so
    a flatten that leaves 14 empty year folders behind has not done the job.

    Three limits, because this deletes directories: only paths UNDER dest, only
    when `os.listdir` says empty, and never dest itself. It removes no file
    under any circumstance - `os.rmdir` refuses a non-empty directory - so the
    worst case is a directory that should have stayed, which `--reverse`
    recreates on the way back.
    """
    gone = []
    for dp, dns, fns in os.walk(lp(dest), topdown=False):
        real = dp.replace("\\\\?\\", "")
        if real.lower().rstrip("\\") == dest.lower().rstrip("\\"):
            continue                      # never the folder itself
        try:
            if not os.listdir(lp(real)):
                os.rmdir(lp(real))
                gone.append(real)
        except OSError as e:
            print("   could not remove {}: {}".format(real, e))
    return gone


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(P.AUDIT, "library.db"))
    ap.add_argument("--dest", default=DEST)
    ap.add_argument("--journal", default=os.path.join(
        P.AUDIT, "intimate-sweep-{}.csv".format(
            dt.datetime.now().strftime("%Y%m%dT%H%M%S"))))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--reverse", default="", metavar="JOURNAL")
    a = ap.parse_args()

    if a.reverse:
        return reverse(a.reverse)
    if a.verify:
        return 0 if verify(a.db, a.dest) == 0 else 1

    rows = plan(a.db, a.dest)
    print("classified intimate, to move: {}".format(len(rows)))
    for k, n in collections.Counter(r["kind"] or "?" for r in rows).most_common():
        print("   {:<12} {:>4}".format(k, n))
    print()
    for r in rows[:6]:
        print("   {}".format(r["source"]))
        print("     -> {}".format(r["destination"]))

    # A destination that already holds a different file stops the run. Two
    # sources can share a basename across years, and silently overwriting one
    # with the other would destroy a photograph to tidy a folder.
    seen, clashes = {}, []
    for r in rows:
        d = r["destination"].lower()
        if d in seen and seen[d] != r["source"]:
            clashes.append((seen[d], r["source"], r["destination"]))
        seen[d] = r["source"]
        if os.path.exists(lp(r["destination"])):
            clashes.append(("(on disk)", r["source"], r["destination"]))
    if clashes:
        print()
        print("STOPPING: {} destination collision(s).".format(len(clashes)))
        for a_, b_, d_ in clashes[:8]:
            print("   {}\n   {}\n   both -> {}".format(a_, b_, d_))
        print("  Nothing moved. Overwriting one photograph with another to")
        print("  tidy a folder is not a trade worth making.")
        return 1

    if not a.apply:
        print()
        print("dry run - nothing moved. Re-run with --apply.")
        return 0

    # THE JOURNAL IS WRITTEN FIRST. If the process dies mid-sweep, the journal
    # already names every intended move and --reverse can undo what happened.
    with io.open(a.journal, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print()
    print("journal written FIRST: {}".format(a.journal))

    moved = 0
    for r in rows:
        os.makedirs(os.path.dirname(lp(r["destination"])), exist_ok=True)
        shutil.move(lp(r["source"]), lp(r["destination"]))
        moved += 1
    print("moved {:,} of {:,}".format(moved, len(rows)))

    pruned = prune_empty(a.dest)
    if pruned:
        print("pruned {} emptied subfolder(s): {}".format(
            len(pruned), ", ".join(sorted(os.path.basename(p)
                                          for p in pruned))))
    left = [n for n in os.listdir(lp(a.dest))
            if os.path.isdir(lp(os.path.join(a.dest, n)))]
    print("subfolders remaining under {}: {}{}".format(
        a.dest, len(left), "  " + ", ".join(sorted(left)) if left else ""))
    print()
    # THE INDEX CANNOT LEARN A MOVE ON ITS OWN. build_db.load_files() reads
    # INVENTORY.csv and the hash index; neither walks the disk. After this sweep
    # I told the operator to rebuild the index, waited 236 seconds for it, and
    # the 88 moved files were STILL listed under their old paths - 0 index rows
    # mention Intimate, and the inventory has not been written since
    # 2026-09-12. apply_split_by_path.py then refused its own approved plan
    # because two sources no longer existed, which is the refusal working.
    print("Now, IN THIS ORDER - the index reads the inventory, not the disk:")
    print("  1. refresh the inventory (stage 04), or the moves are invisible")
    print("  2. python stages/08_index/build_db.py")
    print("  3. sweep_intimate.py --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
