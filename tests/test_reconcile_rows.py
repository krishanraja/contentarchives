r"""An orphan row is derived from its path, or the index inherits a lie.

    python tests\test_reconcile_rows.py

WHY THIS EXISTS

`reconcile_disk.py --write` is the documented way new files reach the records -
RESUME.md names it as the step without which `build_db.py` cannot see anything
`ingest_tree.py` added. It appended 11,742 rows, cleanly, with the right count,
and two of their columns were wrong:

  Year  was left empty although the path names the year, so 11,707 files
        entered the index undated and invisible to every query that asks when.

  Kind  was `"photo" if ext in MEDIA`, and MEDIA holds video extensions too,
        so 4,344 videos were filed as photographs.

Nothing raised. The append succeeded, the counts reconciled, and only the
meaning was wrong - which is the failure mode this repo keeps paying for and
the reason a count is never evidence on its own.

THE COLUMN THAT IS NOT WRONG, AND MUST NOT BE "FIXED"

`Side` holds the TOP-LEVEL TREE - "Media", "Archive", "_Review",
"ContentProduction" - because that is what `build_inventory.py`, which owns the
column, writes (`side = rel[0]`). It is NOT Personal/Communal. Those live one
level further down and are read from the PATH by `side_of`, never from this
column; `people_sheet.py` records what joining on it cost - a filter that
"found no cluster with a Personal photograph, and would have excluded all
58,033" (learning 54).

On 2026-09-22 this column was "corrected" to hold a real side, which made one
column mean two different things in one file, and was changed straight back.
The assertions below are deliberately explicit about the tree so the next
reader who notices that `Side` looks wrong finds out here why it is not.

The month stays empty on purpose. The chronology is one level deep since
2026-09-21 and the path no longer carries a month; deriving one would be
inventing it.
"""

import csv
import importlib.util
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

_spec = importlib.util.spec_from_file_location(
    "reconcile_disk", os.path.join(ROOT, "stages", "04_inventory", "reconcile_disk.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

from contentarchives.sides import side_of                       # noqa: E402

B = chr(92)
FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def lib(*parts):
    return B.join(("D:", "ContentLibrary", "Media") + parts)


def main():
    # 1. SIDE IS THE TREE, NOT THE SIDE. Both of these sit under Media\, so
    #    both must say "Media" - while side_of, reading the same path, gives
    #    the real side. Two different questions, two different answers.
    for side in ("Communal", "Personal"):
        p = lib(side, "2023", "a.jpg")
        check("{} records the TREE in Side, not the side".format(side),
              R.row_for(p, 100, ".jpg")[1], "Media")
        check("  and side_of reads the real side from the same path",
              side_of(p), side)
    check("a tree that is not Media keeps its own name",
          R.row_for(B.join(("D:", "ContentLibrary", "Archive", "x.pdf")),
                    100, ".pdf")[1], "Archive")

    # 2. THE YEAR IS TAKEN FROM THE PATH, WHICH NAMES IT.
    row = R.row_for(lib("Communal", "2019", "b.jpg"), 100, ".jpg")
    check("the year folder becomes the Year column", row[2], "2019")
    check("the month stays empty - the path no longer carries one", row[3], "")

    # A queue is not a year. NoDate has no year folder and must not gain one.
    check("NoDate gets no year invented for it",
          R.row_for(lib("NoDate", "c.jpg"), 100, ".jpg")[2], "")

    # A four-digit filename is not a year folder.
    check("a number in the FILENAME is not read as the year",
          R.row_for(lib("Communal", "2023", "IMG_1234.jpg"), 100, ".jpg")[2],
          "2023")

    # 3. A VIDEO IS NOT A PHOTOGRAPH. MEDIA holds both, which is what made
    #    `"photo" if ext in MEDIA` wrong for 4,344 files.
    for ext, kind in ((".mp4", "video"), (".mov", "video"), (".mts", "video"),
                      (".jpg", "photo"), (".heic", "photo"), (".pdf", "other")):
        check("{:<6} is filed as {}".format(ext, kind),
              R.row_for(lib("Communal", "2023", "x" + ext), 100, ext)[5], kind)

    # 4. THE ROW STILL FITS THE INVENTORY, and still stamps itself so --repair
    #    can find its own output and nothing else.
    row = R.row_for(lib("Communal", "2023", "d.jpg"), 4242, ".jpg")
    check("the row is the inventory's width", len(row), 23)
    check("the path is column 0", row[0], lib("Communal", "2023", "d.jpg"))
    check("the size is carried through", row[6], 4242)
    check("the row stamps itself reconciled-from-disk", row[22],
          "reconciled-from-disk")

    # 5. --repair TOUCHES ONLY ITS OWN ROWS. A row written by a person or by
    #    another stage must come back byte for byte.
    d = tempfile.mkdtemp(prefix="reconcile-")
    inv = os.path.join(d, "INVENTORY.csv")
    header = ["LibraryPath", "Side", "Year", "Month", "Ext", "Kind", "Bytes",
              "DateTaken", "DateSource", "Make", "Model", "Width", "Height",
              "Duration", "Lat", "Lon", "PlaceGuess", "PlaceSource",
              "EventGuess", "FilenameShape", "OriginFolder", "SourceRoot",
              "OriginJoin"]
    mine = ([lib("Communal", "2023", "e.mp4"), "Media", "", "", ".mp4",
             "photo", "99"] + [""] * 15)[:22] + ["reconciled-from-disk"]
    theirs = ([lib("Personal", "2001", "f.jpg"), "Media", "2001", "07",
               ".jpg", "photo", "50"] + [""] * 15)[:22] + ["a-real-origin-join"]
    with io.open(inv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerow(mine)
        w.writerow(theirs)

    R.INVENTORY = inv
    R.repair_rows()
    with io.open(inv, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))[1:]
    check("the tool's own row is corrected",
          (rows[0][1], rows[0][2], rows[0][5]), ("Media", "2023", "video"))
    check("a row it did not write is untouched", rows[1], theirs)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
