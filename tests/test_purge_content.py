r"""A tool that destroys unique content must be tested before it is trusted once.

    python tests\test_purge_content.py

WHY THIS EXISTS

`guarded_delete.py` refuses to delete anything without a proven surviving copy.
`purge_content.py` is the deliberate exception - Krish, 2026-09-18: *"purge all
intimate content forever"* - and it is therefore the only tool here that can
destroy something irreplaceable on purpose. Stage 10 carried no test for it,
and a destructive tool nobody has watched fail is indistinguishable from one
with no guards at all (learning 44).

Every check below runs on a fixture. Nothing in this file can reach the library:
the paths it writes live in a temp directory, and the module's real targets come
only from a `--list` file.

WHAT IS PINNED

  1. A STALE LIST STOPS THE RUN. If a listed path's content no longer hashes to
     what the list claims, nothing is deleted at all - not even the files that
     did verify. A path-substring rule once destroyed 45 irreplaceable files
     here, and re-hashing at the moment of deletion is the defence.
  2. A ROW IS KEPT WHEN A FACE IS PURGED. The embedding is zeroed in place so
     the row holds its position, and therefore the frozen cluster id that 1,609
     human answers point at. Removing the row would shift every later position
     in face-emb.npy (learning 45).
  3. THE ZERO VECTOR IS STILL DECODABLE. An empty `emb` drops the row out of
     cluster_faces.load()'s filter, which is the same positional shift by
     another route. It must decode to 512 zero float16s instead.
  4. --also REFUSES A PATH THAT IS NOT A TARGET, by hash, so a copy outside the
     library can never be deleted on the strength of its name.
  5. --blocklist-also RECORDS WITHOUT DELETING, for content already gone.
"""

import base64
import csv
import io
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

sys.path.insert(0, os.path.join(ROOT, "stages", "10_reclaim"))
import purge_content as PC                                        # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


print("1. the zero vector is a real embedding, not an empty field")
raw = base64.b64decode(PC.ZERO_EMB)
check("it decodes to 512 float16 values", len(raw), 512 * 2)
v = np.frombuffer(raw, dtype=np.float16).astype(np.float32)
check("all of them are zero", bool(not v.any()), True)
check("and it is NOT the empty string, which would drop the row from "
      "cluster_faces.load()'s filter", PC.ZERO_EMB != "", True)

print()
print("2. a stale list stops the whole run, not just the bad row")
import tempfile                                                   # noqa: E402
d = tempfile.mkdtemp()
try:
    good = os.path.join(d, "good.bin")
    io.open(good, "wb").write(b"the real content")
    from store import content_hash                                # noqa: E402
    gh = content_hash(good)

    changed = os.path.join(d, "changed.bin")
    io.open(changed, "wb").write(b"content as listed")
    ch = content_hash(changed)
    io.open(changed, "wb").write(b"CONTENT THAT CHANGED SINCE")

    lst = os.path.join(d, "targets.csv")
    with io.open(lst, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Hash", "Path", "Bytes", "Kind"])
        w.writerow([gh, good, os.path.getsize(good), "photo"])
        w.writerow([ch, changed, 17, "photo"])

    rows = PC.read_list(lst)
    check("both rows are read", len(rows), 2)
    ok, bad = PC.verify(rows)
    check("the unchanged file verifies", [r["Path"] for r in ok], [good])
    check("the changed one is refused", len(bad), 1)
    check("and the refusal says the content changed",
          "CONTENT CHANGED" in bad[0], True)

    # The run must stop. Both files must still exist afterwards.
    cp = subprocess.run(
        [sys.executable, os.path.join(ROOT, "stages", "10_reclaim",
                                      "purge_content.py"),
         "--list", lst, "--apply"],
        capture_output=True, text=True, timeout=180)
    check("the process exits non-zero", cp.returncode != 0, True)
    # Assert on the SIGNAL, not on my memory of the wording. The first version
    # of this check looked for the phrase "Nothing has been touched" and failed
    # while the tool was behaving perfectly: that sentence is printed across
    # three separate print() calls, so no single line contains it. A test that
    # fails on line-wrapping teaches the reader to ignore the test.
    out = (cp.stdout or "") + (cp.stderr or "")
    check("it refuses because the list and the disk disagree",
          "STOPPING" in out and "disagree" in out, True)
    check("the file that DID verify still exists", os.path.exists(good), True)
    check("and so does the one that changed", os.path.exists(changed), True)
    check("no journal was written for a refused run",
          os.path.exists(PC.JOURNAL) is False or
          "good.bin" not in io.open(PC.JOURNAL, encoding="utf-8",
                                    errors="replace").read(),
          True)

    print()
    print("3. --also refuses a path whose hash is not on the list")
    stranger = os.path.join(d, "stranger.bin")
    io.open(stranger, "wb").write(b"not a target at all")
    lst2 = os.path.join(d, "targets2.csv")
    with io.open(lst2, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Hash", "Path", "Bytes", "Kind"])
        w.writerow([gh, good, os.path.getsize(good), "photo"])
    cp = subprocess.run(
        [sys.executable, os.path.join(ROOT, "stages", "10_reclaim",
                                      "purge_content.py"),
         "--list", lst2, "--also", stranger, "--apply"],
        capture_output=True, text=True, timeout=180)
    out = cp.stdout + cp.stderr
    check("the process exits non-zero", cp.returncode != 0, True)
    check("it says the hash is not in the target list",
          "NOT in the target list" in out, True)
    check("the stranger still exists", os.path.exists(stranger), True)
    check("and the real target was not deleted either",
          os.path.exists(good), True)

    print()
    print("4. a purged face row keeps its position")
    faces = os.path.join(d, "faces.csv")
    real = base64.b64encode(
        (np.arange(512, dtype=np.float16) / 512.0).tobytes()).decode()
    with io.open(faces, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "face_index", "bbox", "det_score", "said", "emb"])
        w.writerow(["a" * 64, "0", "1,2,3,4", "0.91", "1", real])
        w.writerow([gh, "0", "9,9,9,9", "0.88", "1", real])
        w.writerow(["c" * 64, "0", "5,6,7,8", "0.80", "1", real])

    targets = {gh.lower()}

    def zero_face(r):
        if not r or r[0].strip().lower() not in targets:
            return r
        out = list(r)
        if len(out) >= 6:
            out[2] = ""
            out[3] = "0.000"
            out[-1] = PC.ZERO_EMB
        return out

    kept, dropped = PC.rewrite_csv(faces, zero_face)
    check("no row was removed", (kept, dropped), (3, 0))
    after = list(csv.DictReader(io.open(faces, encoding="utf-8", newline="")))
    check("the purged row is still in position 2",
          after[1]["hash"], gh)
    check("its bbox is gone", after[1]["bbox"], "")
    check("its detector score is gone", after[1]["det_score"], "0.000")
    zv = np.frombuffer(base64.b64decode(after[1]["emb"]),
                       dtype=np.float16).astype(np.float32)
    check("its embedding is all zeros", bool(not zv.any()), True)
    check("the neighbours are untouched",
          [after[0]["bbox"], after[2]["bbox"]], ["1,2,3,4", "5,6,7,8"])
finally:
    import shutil
    shutil.rmtree(d, ignore_errors=True)

print()
print("5. a derived copy outlives the original it was made from")
# The 2026-09-18 run keyed its trace sweep on `targets` - the files it could
# re-hash and unlink - so for the 7 hashes it could block but not delete it left
# 7 thumbnails, 5 face vectors, 5 bounding boxes and 117 tag rows, including the
# written description of each photograph. The originals were unreachable; their
# likenesses were not.
#
# The rule: a purge is keyed on CONTENT, so a hash worth blocking forever is a
# hash whose every derived copy goes with it.
deletable = {"a" * 64, "b" * 64}
blocked = [("c" * 64, 123, "already absent from disk"),
           ("d" * 64, 456, "already absent from disk")]
got = PC.sweep_set(deletable, blocked)
check("the sweep covers blocked hashes, not just deletable ones",
      got, deletable | {"c" * 64, "d" * 64})
check("with nothing blocked it is exactly the deletable set",
      PC.sweep_set(deletable, []), deletable)
check("a hash that is both deletable and blocked appears once",
      len(PC.sweep_set({"a" * 64}, [("a" * 64, 1, "dup")])), 1)
check("and it is a set, so the caller cannot double-sweep",
      isinstance(got, set), True)

print()
print("6. --traces-only refuses three ways, and every refusal EXITS NON-ZERO")
# The mode exists because `verify()` re-hashes every target at the instant of
# deletion, so a file that has already vanished fails as "already gone" and can
# never be a target - leaving its thumbnail, its description and the vector
# describing the face in it behind.
#
# Each refusal must exit non-zero. A tool that prints STOPPING and exits 0 is
# worse than one that crashes: Invoke-Step reads the exit code, and a chain
# carries on. That is learning 58 from the other side, and my own check of these
# refusals reported rc=0 for all four because `| head -3` was swallowing the
# code - so this asserts the returncode directly and never through a pipe.
PURGE = os.path.join(ROOT, "stages", "10_reclaim", "purge_content.py")
for label, extra_args in (
        ("without --blocklist-also there is nothing to sweep",
         ["--traces-only"]),
        ("--list has no meaning when nothing is deleted",
         ["--traces-only", "--list", "x.csv", "--blocklist-also", "y.csv"]),
        ("--also deletes a file, which this mode has none of",
         ["--traces-only", "--blocklist-also", "y.csv", "--also", "D:\\x.jpg"]),
        ("and --list is still required in the normal mode", [])):
    cp = subprocess.run([sys.executable, PURGE] + extra_args,
                        capture_output=True, text=True, errors="replace")
    check(label, cp.returncode != 0, True)
    check("  ... and it says STOPPING rather than failing silently",
          "STOPPING" in (cp.stdout or "") + (cp.stderr or ""), True)

print()
print("7. the trace sweep ACTS on the same set it COUNTS")
# The counts in the summary have always been computed over `sweep` - targets
# plus block-only hashes - while the three actions keyed on `targets` alone. So
# the summary a person approves the purge from promised 117 tag rows, 5 face
# vectors and 5 bounding boxes, and the sweep then removed fewer. A report that
# overstates what was done is worse than one that understates it, because it is
# the report the decision is made on (learning 61).
#
# This is a SOURCE-LEVEL check, deliberately. Driving main() end-to-end would
# need PC.TAGS, FACES, VFACES, CLUSTERS, THUMBS, BLOCKLIST, JOURNAL and CACHE
# all redirected - and it would STILL reach the real D:\_PhotoAudit, because
# PATH_RECORDS, DISPOSABLE and the intimate-sweep journal sweep are built from
# P.AUDIT directly. A test that deletes the operator's real records to prove a
# deletion works is not a test worth having.
src = io.open(PURGE, encoding="utf-8").read()

# EXACT substrings, not parsed slices.
#
# The first version of this check sliced the source:
#
#     src.split("kept, dropped = rewrite_csv(")[1].split(")")[0]
#
# which cuts at the FIRST ")" - the one closing `lower()` - so the slice ended
# before `in sweep` ever appeared. The positive check failed, and the negative
# check ("no longer on targets") PASSED, because both strings were absent from a
# slice that contained neither. A false pass, in the test written to pin
# learning 61, by exactly the mechanism learning 61 is about: an assertion that
# agreed with me without examining the thing it claimed to examine.
#
# So each site is asserted as the whole expression, and the OLD form is asserted
# absent - a negative that could only pass by the string genuinely being gone.
FIXED = [
    ("content_tags.csv",
     "r[0].strip().lower() in sweep else r)",
     "r[0].strip().lower() in targets else r)"),
    ("zero_face",
     "if not r or r[0].strip().lower() not in sweep:",
     None),           # shares its line shape with strip_cluster; counted below
    ("strip_cluster",
     "if not r or r[0].strip().lower() not in sweep:",
     None),
]
check("content_tags.csv is swept on `sweep`", FIXED[0][1] in src, True)
check("content_tags.csv no longer keys on `targets`", FIXED[0][2] in src, False)

# zero_face and strip_cluster are the two `not in` sites and their guard lines
# are identical, so count rather than locate: BOTH must be on `sweep` and
# NEITHER on `targets`.
check("both face sites key on `sweep`",
      src.count("if not r or r[0].strip().lower() not in sweep:"), 2)
check("and neither still keys on `targets`",
      src.count("if not r or r[0].strip().lower() not in targets:"), 0)

# PATH_RECORDS is the one that must NOT change: a block-only hash has no path
# on record, so there is nothing of it to remove from a path-keyed file.
check("the path records still key on paths, because a blocked hash has none",
      "in dead else r" in src, True)

print()
if FAILURES:
    print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("all checks passed")
