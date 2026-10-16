r"""backup_to_drive.py: the backup drive is refreshed, never relied on.

    python tests\test_backup_to_drive.py

Krish, 2026-10-16: "The external D (currently F) Drive should just be a backup,
nothing should rely on this external drive, everything should be able to be
done on H drive." Pinned here, with a fake H: and a fake backup drive in temp
folders and the cloud faked:

  1. the drive is found by what is on it, under any letter; none plugged in
     is a clean exit 0, not a failure
  2. the cloud's newest export is saved and checked against its sha256; a
     day already there is never overwritten
  3. a photograph the drive lacks is copied from H: and checked against
     Drive's md5; one it holds (mirrored or copied before) is not; a file
     already at the destination is never overwritten
  4. bytes that do not match Drive's md5 stop the run and leave nothing behind
  5. --max-gb stops a run and the next carries on; a dry run writes nothing
"""

import csv
import gzip
import hashlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

import backup_to_drive as B                                      # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<66} {}".format(name, "OK" if ok else "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def md5(b):
    return hashlib.md5(b).hexdigest()


def gz_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return gzip.compress(buf.getvalue().encode("utf-8"), mtime=0)


class FakeCloud:
    """The two PostgREST reads fetch_record makes, bytea as PostgREST sends it."""

    def __init__(self, day, bodies):
        self.day, self.bodies = day, bodies

    def select(self, table, query):
        assert table == "record_exports"
        if "order=day.desc" in query:
            return [{"day": self.day}] if self.day else []
        return [{"name": n, "rows": r, "sha256": hashlib.sha256(b).hexdigest(), "body": "\\x" + b.hex()}
                for n, (r, b) in self.bodies.items()]


def make_drive(root):
    for m in B.MARKERS:
        os.makedirs(os.path.dirname(os.path.join(root, m)), exist_ok=True)
        open(os.path.join(root, m), "wb").close()


def put(root, rel, data):
    p = B.local(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def main():
    t = tempfile.mkdtemp()
    try:
        drive, other, h = (os.path.join(t, n) for n in ("F", "E", "H"))
        os.makedirs(other)
        make_drive(drive)

        print("1. found by what is on it, and never required")
        check("the root holding both markers is the backup drive", B.find_drive([other, drive]), drive)
        check("no root holding them: none", B.find_drive([other]), None)
        out = io.StringIO()
        sys.stdout, old = out, sys.stdout
        try:
            code = B.main(["--drive", other], cloud=FakeCloud(None, {}))
        finally:
            sys.stdout = old
        check("a drive that is not plugged in is a clean exit 0", code, 0)
        check("  and it says nothing waits on it", "nothing waits on it" in out.getvalue(), True)

        # H: holds four photographs; the drive already has one by md5 (mirrored).
        files = {
            "Media/Communal/1985/a.jpg": b"aaa",        # new on H: -> copied
            "Media/Communal/1985/b.jpg": b"bbb",        # mirrored from the drive -> held
            "Media/Personal/NoDate/c.jpg": b"ccc",      # new, and the destination exists -> left alone
            "Media/Communal/1990/d.jpg": b"ddd",        # new -> copied
        }
        for rel, data in files.items():
            put(h, rel, data)
        put(os.path.join(drive, "ContentLibrary"), "Media/Personal/NoDate/c.jpg", b"OLD")
        with open(os.path.join(drive, "_PhotoAudit", "h-mirror.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["path", "blake2b", "md5", "outcome"])
            w.writerow(["x", "bk", md5(b"bbb"), "written"])
        cat_rows = [[md5(d), rel, "drive-" + rel[-5]] for rel, d in files.items()]
        cat_rows.append([md5(b"gone"), "Media/Communal/2000/e.jpg", "drive-e"])   # not on H: now
        cat_rows.append(["", "Media/Communal/2000/f.jpg", ""])                     # no md5: skipped
        bodies = {"answers": (1, gz_csv(["id", "field"], [["1", "in_photo"]])),
                  "journal": (0, gz_csv(["id"], [])),
                  "catalogue": (len(cat_rows), gz_csv(["md5", "rel_path", "drive_id"], cat_rows))}
        cloud = FakeCloud("2026-10-16", bodies)

        print()
        print("2. the cloud's record, saved and checked")
        day, rec = B.fetch_record(cloud)
        check("the newest night is fetched, bytea decoded", (day, sorted(rec)), ("2026-10-16", sorted(B.NAMES)))
        check("a dry run saves nothing", (B.save_record(drive, day, rec, False),
              os.path.exists(os.path.join(drive, "_cloud-record"))), ([], False))
        check("--apply saves all three, each matching its sha256", B.save_record(drive, day, rec, True), [])
        saved = os.path.join(drive, "_cloud-record", "2026-10-16", "answers.csv.gz")
        check("  as readable gzip'd CSV", gzip.decompress(open(saved, "rb").read()).decode().splitlines()[1],
              "1,in_photo")
        check("a second run finds the same bytes and skips", B.save_record(drive, day, rec, True), [])
        with open(saved, "wb") as f:
            f.write(b"different")
        check("a different copy already there is left alone and reported",
              B.save_record(drive, day, rec, True), ["answers: a different copy for 2026-10-16 is already there, left alone"])
        check("  and was not overwritten", open(saved, "rb").read(), b"different")

        print()
        print("3. photographs the drive lacks, copied from H: and checked")
        rows = B.catalogue_rows(rec)
        held = B.held_md5s(drive)
        dry = B.copy_photos(rows, held, h, drive, 1 << 30, apply=False)
        check("a dry run finds what it would copy and copies nothing",
              (dry["copied"], os.path.exists(B.local(os.path.join(drive, "ContentLibrary"), "Media/Communal/1985/a.jpg"))),
              (2, False))
        c = B.copy_photos(rows, held, h, drive, 1 << 30, apply=True)
        lib = os.path.join(drive, "ContentLibrary")
        check("two new photographs copied, byte for byte",
              (c["copied"], open(B.local(lib, "Media/Communal/1985/a.jpg"), "rb").read(),
               open(B.local(lib, "Media/Communal/1990/d.jpg"), "rb").read()), (2, b"aaa", b"ddd"))
        check("one the drive already holds (mirrored) is not copied",
              os.path.exists(B.local(lib, "Media/Communal/1985/b.jpg")), False)
        check("a file already at the destination is never overwritten",
              (c["already-there"], open(B.local(lib, "Media/Personal/NoDate/c.jpg"), "rb").read()), (1, b"OLD"))
        check("one gone from H: is counted, not an error", c["missing-on-h"], 1)
        check("every copy is journalled", sorted(
            r["outcome"] for r in csv.DictReader(open(B.journal_path(drive), encoding="utf-8"))),
            ["already-there", "copied", "copied"])
        again = B.copy_photos(rows, B.held_md5s(drive), h, drive, 1 << 30, apply=True)
        check("a second run copies nothing it already copied", again["copied"], 0)

        print()
        print("4. bytes that do not match Drive's md5 stop the run")
        put(h, "Media/Communal/2001/g.jpg", b"corrupted")
        put(h, "Media/Communal/2002/h.jpg", b"hhh")
        bad = [{"md5": md5(b"what Drive holds"), "rel_path": "Media/Communal/2001/g.jpg"},
               {"md5": md5(b"hhh"), "rel_path": "Media/Communal/2002/h.jpg"}]
        c = B.copy_photos(bad, set(), h, drive, 1 << 30, apply=True)
        check("the run stops at the mismatch", (c["mismatch"], c["copied"]), ("Media/Communal/2001/g.jpg", 0))
        check("  and leaves no file or partial file behind",
              [f for f in os.listdir(os.path.dirname(B.local(lib, "Media/Communal/2001/g.jpg")))]
              if os.path.isdir(os.path.dirname(B.local(lib, "Media/Communal/2001/g.jpg"))) else [], [])
        check("  and the photograph after it waits for the next run",
              os.path.exists(B.local(lib, "Media/Communal/2002/h.jpg")), False)

        print()
        print("5. --max-gb stops a run; the next carries on")
        for n in range(3):
            put(h, "Media/Communal/2003/{}.jpg".format(n), bytes([n]) * 100)
        more = [{"md5": md5(bytes([n]) * 100), "rel_path": "Media/Communal/2003/{}.jpg".format(n)}
                for n in range(3)]
        c = B.copy_photos(more, set(), h, drive, 150, apply=True)
        check("a budget of 150 bytes copies two 100-byte files and stops", (c["copied"], c["budget"]), (2, 1))
        c = B.copy_photos(more, B.held_md5s(drive), h, drive, 150, apply=True)
        check("the next run copies the rest", c["copied"], 1)
    finally:
        shutil.rmtree(t, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
