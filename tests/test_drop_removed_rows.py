r"""The tool that stops deleted content coming back wrote nonsense into the ledger.

    python tests\test_drop_removed_rows.py

WHY THIS EXISTS

`drop_removed_rows.py` drops ledger rows for files a human deliberately removed,
and with `--block` it appends their hashes to `PURGED-HASHES.csv` - the
no-reingest list, the only thing standing between a purged file and the ten
phones still to be ingested.

Its first run, on the seven files Krish removed from the Intimate folder,
appended this:

    73208,IMG-20211121-WA0000.jpg,"removed by Krish on purpose",2026-09-18T...

against a header of `Hash,Bytes,Reason,When`. A SIZE in the Hash column and a
FILENAME in the Bytes column, because `hashes_for()` read column 1 of
MIGRATION-HASHES.csv as the hash when that column is the size - the layout is
`path, bytes, hash`. Seven files were reported as blocked and none of them were.
The rows could never match a real hash, and they break any reader parsing
`Bytes` as an integer.

Nobody would have noticed until a phone re-admitted one of the files, months
later, with the blocklist reporting 95 entries the whole time. Stage 04 had no
tests at all, which is how a tool can corrupt a durable ledger on its first use.

WHAT IS PINNED

  1. THE HASH IS FOUND BY SHAPE, NOT POSITION - 64 hex characters - so a record
     laid out `path, bytes, hash` yields the hash and never the size.
  2. THE SIZE COMES BACK TOO, and it is a number, not a filename.
  3. THE BLOCKLIST COLUMNS ARE IN THE HEADER'S ORDER: Hash, Bytes, Reason, When.
  4. A LISTED PATH THAT STILL EXISTS STOPS THE WHOLE RUN. Absence is a
     precondition here, never the reason: `reconcile_disk.py` is additive by
     design because an unmounted drive makes thousands of files look absent, and
     a tool that drops rows for absent paths would destroy the record of a
     200,000-file process the first time one happened.
  5. THE ORIGINAL IS KEPT as a .bak before any rewrite.
"""

import csv
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "stages", "04_inventory"))

import drop_removed_rows as D                                    # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<64} {}".format(
        name, "OK" if ok else "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


HASH_A = "8c2251b437c0d4e679bbed97daabb391d331bb02c946766c7b8119327014e891"
HASH_B = "30bdf8468c41d70683ddab8931319e2490e22b905a2d482ded37a4246b2c0c8a"

tmp = tempfile.mkdtemp(prefix="droprows-test-")
_real_audit = D.AUDIT
_real_block = D.BLOCKLIST
_real_journal = D.JOURNAL
try:
    D.AUDIT = tmp
    D.BLOCKLIST = os.path.join(tmp, "PURGED-HASHES.csv")
    D.JOURNAL = os.path.join(tmp, "ledger-row-drops.csv")

    # Two paths that do NOT exist - the victims.
    gone_a = os.path.join(tmp, "gone", "IMG-A.jpg")
    gone_b = os.path.join(tmp, "gone", "IMG-B.jpg")
    kept = os.path.join(tmp, "kept.jpg")
    io.open(kept, "w").write("still here")

    # MIGRATION-HASHES.csv: HEADERLESS, and laid out path, BYTES, HASH.
    with io.open(os.path.join(tmp, "MIGRATION-HASHES.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([gone_a, "73208", HASH_A])
        w.writerow([gone_b, "107923", HASH_B])
        w.writerow([kept, "999", "f" * 64])

    # INVENTORY.csv: a header record, with the hash NOT in column 1.
    with io.open(os.path.join(tmp, "INVENTORY.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["LibraryPath", "Bytes", "Ext", "Hash"])
        w.writerow([gone_a, "73208", ".jpg", HASH_A])
        w.writerow([gone_b, "107923", ".jpg", HASH_B])
        w.writerow([kept, "999", ".jpg", "f" * 64])

    print()
    print("1. the hash is found by SHAPE, never by column position")
    targets = {D.norm(gone_a), D.norm(gone_b)}
    found = D.hashes_for(targets)
    check("both victims resolved", len(found), 2)
    check("the hash is the 64-hex value, not the size",
          found[D.norm(gone_a)][0], HASH_A)
    check("and not the size that sits in column 1",
          found[D.norm(gone_a)][0] == "73208", False)
    check("the second victim too", found[D.norm(gone_b)][0], HASH_B)
    check("a path that was NOT named is left alone",
          D.norm(kept) in found, False)

    print()
    print("2. the size comes back as a number, not a filename")
    check("bytes for the first victim", found[D.norm(gone_a)][1], "73208")
    check("bytes for the second victim", found[D.norm(gone_b)][1], "107923")
    check("it is not the basename",
          found[D.norm(gone_a)][1] == os.path.basename(gone_a), False)

    print()
    print("3. hashlike accepts a digest and refuses everything else")
    check("a 64-hex digest", D.hashlike(HASH_A), True)
    check("uppercase too", D.hashlike(HASH_A.upper()), True)
    check("a byte count", D.hashlike("73208"), False)
    check("a filename", D.hashlike("IMG-20211121-WA0000.jpg"), False)
    check("a timestamp", D.hashlike("2026-09-18T21:41:20"), False)
    check("63 hex characters", D.hashlike("a" * 63), False)
    check("a non-string", D.hashlike(None), False)

    print()
    print("4. a listed path that STILL EXISTS stops the whole run")
    listfile = os.path.join(tmp, "victims.txt")
    io.open(listfile, "w", encoding="utf-8").write(
        "{}\n{}\n{}\n".format(gone_a, gone_b, kept))
    before = io.open(os.path.join(tmp, "INVENTORY.csv"), encoding="utf-8").read()
    argv = sys.argv
    try:
        sys.argv = ["drop_removed_rows.py", "--list", listfile, "--apply",
                    "--block"]
        rc = D.main()
    finally:
        sys.argv = argv
    after = io.open(os.path.join(tmp, "INVENTORY.csv"), encoding="utf-8").read()
    check("it returns 2 rather than proceeding", rc, 2)
    check("and the record is untouched", after, before)
    check("and no blocklist was created", os.path.exists(D.BLOCKLIST), False)

    print()
    print("5. with only absent paths named, it drops, backs up, and blocks")
    io.open(listfile, "w", encoding="utf-8").write(
        "{}\n{}\n".format(gone_a, gone_b))
    argv = sys.argv
    try:
        sys.argv = ["drop_removed_rows.py", "--list", listfile, "--apply",
                    "--block", "--reason", "removed on purpose"]
        rc = D.main()
    finally:
        sys.argv = argv
    check("it succeeds", rc, 0)

    inv = list(csv.DictReader(io.open(os.path.join(tmp, "INVENTORY.csv"),
                                      encoding="utf-8", newline="")))
    check("INVENTORY keeps only the surviving row", len(inv), 1)
    check("and it is the one that still exists",
          D.norm(inv[0]["LibraryPath"]), D.norm(kept))
    check("the original is kept as a .bak",
          os.path.exists(os.path.join(tmp, "INVENTORY.csv.bak-rowdrop")), True)

    mig = list(csv.reader(io.open(os.path.join(tmp, "MIGRATION-HASHES.csv"),
                                  encoding="utf-8", newline="")))
    check("the headerless record kept only the survivor", len(mig), 1)

    print()
    print("6. the blocklist columns are in the header's order")
    rows = list(csv.reader(io.open(D.BLOCKLIST, encoding="utf-8", newline="")))
    check("header first", rows[0], ["Hash", "Bytes", "Reason", "When"])
    body = rows[1:]
    check("two hashes blocked", len(body), 2)
    check("column 0 is a real hash in every row",
          all(D.hashlike(r[0]) for r in body), True)
    check("column 1 is a byte count in every row",
          all(r[1].isdigit() for r in body), True)
    by = {r[0]: r for r in body}
    check("the first victim's hash is present", HASH_A in by, True)
    check("with its real size", by[HASH_A][1], "73208")
    check("the reason is carried", by[HASH_A][2], "removed on purpose")

    print()
    print("7. the drop journal records the hash, not the size")
    jrows = list(csv.DictReader(io.open(D.JOURNAL, encoding="utf-8",
                                        newline="")))
    check("a row per named file", len(jrows), 2)
    check("every journalled hash is a real hash",
          all(D.hashlike(r["hash"]) for r in jrows), True)

    print()
    print("8. an empty list is refused rather than treated as 'nothing to do'")
    empty = os.path.join(tmp, "empty.txt")
    io.open(empty, "w", encoding="utf-8").write("# only a comment\n")
    argv = sys.argv
    try:
        sys.argv = ["drop_removed_rows.py", "--list", empty, "--apply"]
        rc = D.main()
    finally:
        sys.argv = argv
    check("it returns non-zero", rc != 0, True)

finally:
    D.AUDIT = _real_audit
    D.BLOCKLIST = _real_block
    D.JOURNAL = _real_journal
    shutil.rmtree(tmp, ignore_errors=True)

print()
if FAILURES:
    print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("all checks passed")
sys.exit(0)
