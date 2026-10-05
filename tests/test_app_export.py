r"""The library export carries the knowledge up and nothing private with it.

    python tests\test_app_export.py

stages/13_app/export_library.py is written ONCE, into Google Drive, and then
the cloud is the system of record (stages/13_app/LIBRARY-EXPORT.md). There is
no second chance to notice that a Personal photograph, an adult nude or a
purged file travelled with it, so every rule the contract names is watched
HOLDING, on fixtures built here - synthetic names, synthetic paths, no family
and no library (learning 44).

The fixtures are deliberately hostile:

  * the same bytes filed in both Communal and Personal
  * an adult nude and a purged hash that both still sit under Media\Communal
  * a purged hash the library no longer indexes at all, known only by its md5
  * face rows whose embedding CSV is SHUFFLED, so a positional read gives the
    wrong face and this test says so (learning 45)
  * a journal with answers against targets that are not exported

Run `python tests\test_app_export.py --break <rule>` to see a rule fail on
purpose; `--break list` names them. Every one is exercised by main().
"""

import argparse
import base64
import csv
import io
import json
import os
import shutil
import sqlite3
import struct
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import stagepath  # noqa: E402,F401

import export_library as X                                       # noqa: E402

FAILURES = []
ROOT = r"X:\ContentLibrary"
COM = ROOT + r"\Media\Communal\2014"
BROKEN = ("communal-only-off", "nudity-reason-lost", "purged-not-held",
          "embedding-by-position", "mirror-word-wrong", "no-partial-rename")


def check(name, got, want):
    ok = got == want
    print("  {:<64} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def h(n):
    return "{:064x}".format(n)


# A hash per fixture. The numbers are the only identity here: nothing in this
# file is a real path, a real hash or anybody's name.
H_PLAIN, H_VIDEO, H_BOTH, H_NUDE, H_PURGED, H_PERSONAL, H_BATH, H_GONE = (
    h(n) for n in range(1, 9))

FILES = [
    # (hash, paths, media)
    (H_PLAIN,    [COM + r"\a.jpg"],                                  "photo"),
    (H_VIDEO,    [COM + r"\v.mp4"],                                   "video"),
    (H_BOTH,     [COM + r"\b.jpg", ROOT + r"\Media\Personal\2014\b.jpg"], "photo"),
    (H_NUDE,     [COM + r"\n.jpg"],                                   "photo"),
    (H_PURGED,   [COM + r"\p.jpg"],                                   "photo"),
    (H_PERSONAL, [ROOT + r"\Media\Personal\2014\x.jpg"],              "photo"),
    (H_BATH,     [COM + r"\bath.jpg"],                                "photo"),
]
RESOLVED = {
    H_NUDE: {"sensitivity": "none"},
    H_BATH: {"sensitivity": "private-family"},
}
SENS = {
    H_NUDE: {"nudity": "full", "subject_age": "adult", "sexual": "no"},
    H_BATH: {"nudity": "full", "subject_age": "child", "sexual": "no"},
}
EXPORTED = {H_PLAIN, H_VIDEO, H_BATH}
THUMB = (400, 300)
# cluster -> group, after the merge file
MERGES = {"c2": "c1"}


def emb(seed, dim):
    r = np.random.RandomState(seed)
    v = r.normal(size=dim).astype("float32")
    return v / np.linalg.norm(v)


def md5_of(hh):
    return "md5" + hh[:29]


def write_csv(path, header, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def fixtures(tmp, broken=""):
    """A whole synthetic library on disk, and the args that read it."""
    db_path = os.path.join(tmp, "library.db")
    db = sqlite3.connect(db_path)
    db.executescript("""
      CREATE TABLE files (path TEXT, hash TEXT, media TEXT, date_taken TEXT,
                          year INT, width INT, height INT);
      CREATE TABLE tags (hash TEXT, tag TEXT, value TEXT, source TEXT,
                         confidence REAL, when_ TEXT);
      CREATE TABLE resolved (hash TEXT, field TEXT, value TEXT, source TEXT,
                             confidence REAL);
      CREATE TABLE photo_people (hash TEXT, person TEXT);
    """)
    for hh, paths, media in FILES:
        for p in paths:
            db.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?)",
                       (p, hh, media, "2014-06-01 10:00:00", 2014, 1600, 1200))
        base = {"audience": "family", "sensitivity": "none", "kind": "photo",
                "description": "a description", "place": "a place"}
        base.update(RESOLVED.get(hh, {}))
        for f, v in base.items():
            db.execute("INSERT INTO resolved VALUES (?,?,?,?,?)",
                       (hh, f, v, "x", 1.0))
        for t, v in SENS.get(hh, {}).items():
            db.execute("INSERT INTO tags VALUES (?,?,?,?,?,?)",
                       (hh, t, v, "sens", 1.0, "2026"))
        db.execute("INSERT INTO photo_people VALUES (?,?)", (hh, "NAME-A"))
    db.commit()
    db.close()

    # the no-reingest ledger: one hash the library still indexes, one it does not
    write_csv(os.path.join(tmp, "PURGED-HASHES.csv"), ["Hash", "Bytes"],
              [[H_PURGED, 10], [H_GONE, 20]])

    # The mirror journal: blake2b -> the md5 the cloud finds the file by. The
    # outcome word is the one stage 11 actually WRITES, and a row whose copy
    # failed carries an md5 that describes nothing on Drive.
    ok = "written" if broken != "mirror-word-wrong" else "ok"
    write_csv(os.path.join(tmp, "h-mirror.csv"),
              ["when", "source", "dest", "bytes", "blake2b", "md5", "outcome"],
              [["2026", "s", "d", 1, hh, md5_of(hh), ok]
               for hh, _, _ in FILES if hh != H_VIDEO] +
              [["2026", "s", "d", 1, H_GONE, md5_of(H_GONE), ok],
               ["2026", "s", "d", 1, H_VIDEO, md5_of(H_VIDEO),
                "copy failed: [Errno 2] No such file or directory"]])

    # face assignments: two clusters that merge into one group
    photo_faces = [(H_PLAIN, 0, "c1", 0.99, "40,30,160,150"),
                   (H_PLAIN, 1, "c2", 0.80, "200,30,260,110"),
                   (H_BATH, 0, "c1", 0.90, "10,10,390,290"),
                   (H_NUDE, 0, "c3", 0.95, "40,30,160,150")]
    write_csv(os.path.join(tmp, "FACE-CLUSTERS.csv"),
              ["hash", "face_index", "cluster", "det_score", "bbox"],
              [list(r) for r in photo_faces])
    video_faces = [(H_VIDEO, "vf1", 0, "c1", 0.70, "5,5,55,65", "det")]
    write_csv(os.path.join(tmp, "FACE-CLUSTERS-VIDEO.csv"),
              ["hash", "image", "face_index", "cluster", "det_score", "bbox", "how"],
              [list(r) for r in video_faces])
    write_csv(os.path.join(tmp, "CLUSTER-MERGES.csv"),
              ["cluster", "group", "person", "source"],
              [[c, g, "NAME-A", "human"] for c, g in MERGES.items()])

    # the embedding CSVs, SHUFFLED relative to the assignment order: a reader
    # that joins by position gets a different face's vector (learning 45)
    def b64(v):
        return base64.b64encode(v.astype("float16").tobytes()).decode()

    want = {}
    rows = []
    for i, (hh, fi, _, _, _) in enumerate(photo_faces):
        v = emb(100 + i, X.FACE_DIM)
        want["{}::{}".format(hh, fi)] = v
        rows.append([hh, fi, "0,0,0,0", 0.9, "", b64(v)])
    rows = rows[::-1]
    if broken == "embedding-by-position":
        rows = [r[:5] + [rows[(i + 1) % len(rows)][5]]
                for i, r in enumerate(rows)]
    write_csv(os.path.join(tmp, "faces.0.csv"),
              ["hash", "face_index", "bbox", "det_score", "said", "emb"], rows)

    vrows = []
    for i, (hh, im, fi, _, _, _, _) in enumerate(video_faces):
        v = emb(200 + i, X.FACE_DIM)
        want["{}:{}:{}".format(hh, im, fi)] = v
        vrows.append([hh, im, fi, "0,0,0,0", 0.7, b64(v)])
    write_csv(os.path.join(tmp, "faces.video.csv"),
              ["hash", "image", "face_index", "bbox", "det_score", "emb"], vrows)

    # description vectors, one shard, in an order nothing may rely on
    hs = [H_BATH, H_PLAIN, H_VIDEO, H_NUDE]
    vecs = {hh: emb(300 + i, X.DESC_DIM) for i, hh in enumerate(hs)}
    np.savez(os.path.join(tmp, "desc-vectors", "shard-0000.npz"),
             hash=np.array(hs), vec=np.stack([vecs[k] for k in hs]))

    json.dump({"events": [{"start": "2014-06-01", "hashes": [H_PLAIN, H_BATH]}]},
              io.open(os.path.join(tmp, "EVENTS.json"), "w", encoding="utf-8"))

    # the journal: two exported targets, two that are not
    write_csv(os.path.join(tmp, "answers.csv"),
              ["when", "scope", "target", "field", "value", "confidence",
               "who", "note"],
              [["2026-09-01T10:00:00", "cluster", "c1", "person", "NAME-A",
                "1.00", "player-a", ""],
               ["2026-09-02T10:00:00", "cluster", "c1", "person", "NAME-B",
                "1.00", "player-a", "a correction"],
               ["2026-09-03T10:00:00", "file", H_PLAIN, "place", "a place",
                "1.00", "player-b", ""],
               ["2026-09-04T10:00:00", "file", H_PERSONAL, "place", "nowhere",
                "1.00", "player-b", ""],
               ["2026-09-05T10:00:00", "cluster", "c9", "person", "NAME-C",
                "1.00", "player-b", ""]])

    a = argparse.Namespace(
        db=db_path,
        assign=os.path.join(tmp, "FACE-CLUSTERS.csv"),
        video_assign=os.path.join(tmp, "FACE-CLUSTERS-VIDEO.csv"),
        merges=os.path.join(tmp, "CLUSTER-MERGES.csv"),
        vectors=os.path.join(tmp, "desc-vectors"),
        events=os.path.join(tmp, "EVENTS.json"),
        mirror=os.path.join(tmp, "h-mirror.csv"),
        blocklist=os.path.join(tmp, "PURGED-HASHES.csv"),
        answers=os.path.join(tmp, "answers.csv"),
        faces=os.path.join(tmp, "faces.0.csv"),
        video_faces=os.path.join(tmp, "faces.video.csv"),
        thumbs=os.path.join(tmp, "thumbs"),
        out=os.path.join(tmp, "out", "archives-library.sqlite"))
    return a, want, vecs


def quiet(*_a, **_k):
    pass


def main(broken=""):
    tmp = tempfile.mkdtemp(prefix="export-test-")
    try:
        os.makedirs(os.path.join(tmp, "desc-vectors"))
        a, want_faces, want_desc = fixtures(tmp, broken)
        b = X.build(a, size_of=lambda p: THUMB, log=quiet)
        photos = {r[0]: r for r in b["photos"]}
        held = {r[0]: r for r in b["held"]}
        faces = {r[0]: r for r in b["faces"]}

        print("rule 1: Communal only, and nothing else EVER")
        check("the exported hashes are exactly the share set",
              set(photos), EXPORTED)
        check("a Personal photograph is not exported", H_PERSONAL in photos, False)
        check("a Personal photograph is not even held (not on that side of Drive)",
              H_PERSONAL in held, False)
        check("the same bytes also filed in Personal are not exported",
              H_BOTH in photos, False)
        check("every rel_path is under Media/Communal/",
              all(r[2].startswith("Media/Communal/") for r in b["photos"]), True)

        print()
        print("rule 2: everything held out stays held out")
        check("an adult nude lands in held", held.get(H_NUDE, (0, 0, 0, ""))[3],
              "nudity")
        check("a purged hash the library still indexes is held as 'removed'",
              held.get(H_PURGED, (0, 0, 0, ""))[3], "removed")
        check("a purged hash the library does NOT index is held by md5 alone",
              held.get(H_GONE, (0, 0, 0, ""))[3], "removed")
        check("that one has an md5 and no path",
              H_GONE in held and bool(held[H_GONE][1])
              and held[H_GONE][2] is None, True)
        check("the Communal copy of a both-sides file is held",
              held.get(H_BOTH, (0, 0, 0, ""))[3], "outside-communal")
        check("no reason is ever a description of the content",
              all(len(r[3].split()) == 1 for r in b["held"]), True)

        print()
        print("the md5 is how the cloud finds the file on Drive")
        check("a photograph carries the md5 the mirror journal recorded",
              photos[H_PLAIN][1], md5_of(H_PLAIN))
        check("every exported photograph the journal covers has one",
              {hh for hh, r in photos.items() if r[1]}, EXPORTED - {H_VIDEO})
        check("a row whose copy FAILED contributes no md5",
              photos[H_VIDEO][1], None)
        check("a purged hash is named by md5 even with no path",
              held.get(H_GONE, (0, None))[1], md5_of(H_GONE))

        print()
        print("rule 3: joined by key, never by position (learning 45)")
        for k, v in sorted(want_faces.items()):
            if k not in faces:
                continue
            got = np.frombuffer(faces[k][14], dtype="<f4")
            check("face ...{} carries ITS OWN embedding".format(k[-8:]),
                  bool(np.allclose(got, v, atol=2e-3)), True)
        check("every exported photograph the shard describes has a vector",
              {hh for hh, r in photos.items() if r[19]},
              set(photos) & set(want_desc))
        for hh, r in sorted(photos.items()):
            if r[19] is None:
                continue
            got = np.frombuffer(r[19], dtype="<f4")
            check("photo ...{} carries ITS OWN description vector".format(hh[-4:]),
                  bool(np.allclose(got, want_desc[hh], atol=2e-3)), True)

        print()
        print("the blobs are the width and the length the contract promises")
        check("a description vector is 768 x float32",
              {len(r[19]) for r in b["photos"] if r[19]}, {X.DESC_DIM * 4})
        check("a face vector is 512 x float32",
              {len(r[14]) for r in b["faces"]}, {X.FACE_DIM * 4})
        check("every face vector is unit length",
              all(abs(float(np.linalg.norm(np.frombuffer(r[14], dtype="<f4"))) - 1)
                  < 1e-4 for r in b["faces"]), True)

        print()
        print("a bbox is a FRACTION of the thumbnail it was measured on")
        k = "{}::0".format(H_PLAIN)
        check("x1,y1,x2,y2 are the pixel box over the thumbnail",
              [round(v, 4) for v in faces[k][5:9]],
              [round(40 / 400, 4), round(30 / 300, 4),
               round(160 / 400, 4), round(150 / 300, 4)])
        check("thumb_w, thumb_h are that thumbnail's pixels",
              list(faces[k][9:11]), list(THUMB))
        check("share is the face's short edge over the thumbnail's",
              round(faces[k][12], 4), round(120 / 300.0, 4))
        check("a video face has no box and no share",
              list(faces["{}:vf1:0".format(H_VIDEO)][5:9]) +
              [faces["{}:vf1:0".format(H_VIDEO)][12]], [None] * 5)
        check("only_face is 0 where the photograph has two faces",
              faces[k][13], 0)
        check("a face on a held-out photograph is not exported",
              any(r[1] == H_NUDE for r in b["faces"]), False)
        check("every face hangs off an exported hash",
              {r[1] for r in b["faces"]} <= set(photos), True)
        check("every face names a cluster the clusters table holds",
              {r[4] for r in b["faces"]} <= {c for c, _ in b["clusters"]}, True)
        check("the merge file decides the group, people decided the merge",
              dict(b["clusters"]).get("c2"), "c1")

        print()
        print("answers are limited to exported targets, verbatim, oldest first")
        check("only exported clusters and hashes",
              {r[4] for r in b["answers"]}, {"c1", H_PLAIN})
        check("a correction is kept beside what it corrects",
              [r[6] for r in b["answers"] if r[4] == "c1"],
              ["NAME-A", "NAME-B"])
        check("oldest first", [r[1] for r in b["answers"]] ==
              sorted(r[1] for r in b["answers"]), True)
        check("the id is uuid5 over the row's own content",
              b["answers"][0][0], X.answer_id(
                  {"when": "2026-09-01T10:00:00", "who": "player-a",
                   "scope": "cluster", "target": "c1", "field": "person",
                   "value": "NAME-A"}))
        check("an answer against an unexported target is dropped",
              any(r[4] in (H_PERSONAL, "c9") for r in b["answers"]), False)

        print()
        print("atomic: a .partial, verified, then renamed (rule 6)")
        out, part = a.out, a.out + ".partial"
        if broken == "no-partial-rename":
            X.write(b, out, log=quiet)
            os.rename(out, part)                    # left half-written on Drive
        else:
            X.write(b, out, log=quiet)
        check("the final file exists", os.path.exists(out), True)
        check("no .partial is left behind", os.path.exists(part), False)
        if not os.path.exists(out):
            FAILURES.append("nothing to reopen")
            return 1
        got = sqlite3.connect(out)
        try:
            for t in X.COLUMNS:
                check("reopened: {} holds what was built".format(t),
                      got.execute("select count(*) from " + t).fetchone()[0],
                      len(b[t]))
            meta = dict(got.execute("select key, value from meta"))
            check("meta says format 1", meta.get("format"), "1")
            check("meta carries no path and no name",
                  any(ch in "".join(meta.values()) for ch in ("\\", ":\\")), False)
            check("meta's counts agree with the tables",
                  json.loads(meta["counts"])["photos"], len(b["photos"]))
        finally:
            got.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


def break_one(rule):
    """Break one rule in the PRODUCTION code on purpose, and insist the test
    above catches it. A filter nobody has seen reject is indistinguishable from
    no filter, and that is just as true of the test as of the filter."""
    import share_set as S
    if rule == "communal-only-off":
        S.path_ok = lambda p: True            # rule 1 disabled
    elif rule == "nudity-reason-lost":
        X.reason_word = lambda why: "other"   # held, but not as nudity
    elif rule == "purged-not-held":
        X.blocked_hashes = lambda *_a, **_k: set()
    try:
        return main(rule)
    except BaseException as e:                                   # noqa: BLE001
        print()
        print("  the code refused outright: {}: {}".format(
            type(e).__name__, str(e)[:120]))
        return 1


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--break":
        rule = sys.argv[2] if len(sys.argv) > 2 else "list"
        if rule == "list":
            print("\n".join(BROKEN))
            sys.exit(0)
        rc = break_one(rule)
        print()
        print("breaking {!r} made the test {}".format(
            rule, "FAIL, as it must" if rc else "PASS - THE TEST HAS A HOLE"))
        sys.exit(0 if rc else 1)
    sys.exit(main())
