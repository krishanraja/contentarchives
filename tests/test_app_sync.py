r"""The seed sends only what may be shared; the pull lands answers once, under the right name.

    python tests\test_app_sync.py

stages/13_app/seed_index.py builds the family app's cloud index from the
library, and pull_answers.py brings the family's answers back. Both run
unattended on the library machine. Pinned here, each watched failing as well
as passing:

  1. a Personal photograph never reaches the queue, a sample, a cover face or
     the people list, even inside a group that is mostly Communal
  2. a video face is used only once its OWN frame has a verdict that clears
     the nudity rule
  3. suggestions come from embeddings joined by key, never by position
  4. one "label the whole day" tap becomes one journal row per photograph,
     and the cloud row is ingested only if all of them were
  5. a pull that died after recording but before marking is finished by the
     next run, not left `new` forever
"""

import base64
import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import stagepath  # noqa: E402,F401

import numpy as np                                               # noqa: E402
import seed_index as SI                                          # noqa: E402
import pull_answers as PA                                        # noqa: E402

FAILURES = []
C = "D:\\ContentLibrary\\Media\\Communal\\2014\\"
PERS = "D:\\ContentLibrary\\Media\\Personal\\2014\\"


def check(name, got, want):
    ok = got == want
    print("  {:<64} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def h(n):
    return "{:064x}".format(n)


def write(path, header, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def emb(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float16)
    return base64.b64encode(v.tobytes()).decode()


def fixture(d):
    db = sqlite3.connect(os.path.join(d, "library.db"))
    db.executescript("""
      CREATE TABLE files (path TEXT, hash TEXT, media TEXT, date_taken TEXT,
                          year TEXT, width INT, height INT);
      CREATE TABLE tags (hash TEXT, tag TEXT, value TEXT, source TEXT, confidence REAL, when_ TEXT);
      CREATE TABLE resolved (hash TEXT, field TEXT, value TEXT, source TEXT, confidence REAL);
      CREATE TABLE photo_people (hash TEXT, person TEXT, source TEXT);
    """)
    # 1-4 Communal photos, 5 a Personal photo, 6 a Communal video
    paths = {1: C + "a.jpg", 2: C + "b.jpg", 3: C + "c.jpg", 4: C + "d.jpg",
             5: PERS + "p.jpg", 6: C + "v.mp4"}
    for n, p in paths.items():
        db.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?)",
                   (p, h(n), "video" if p.endswith(".mp4") else "photo",
                    "2014-06-0{} 12:00:00".format(n), "2014", 512, 384))
        for f, v in (("audience", "family"), ("sensitivity", "none"), ("kind", "photo"),
                     ("description", "photo number {}".format(n))):
            db.execute("INSERT INTO resolved VALUES (?,?,?,?,?)", (h(n), f, v, "x", 1.0))
    db.execute("INSERT INTO photo_people VALUES (?,?,?)", (h(1), "Asha Raja", "human"))
    db.execute("INSERT INTO photo_people VALUES (?,?,?)", (h(5), "Personal Friend", "human"))
    db.commit()
    db.close()
    # faces: c1 = Asha (named), photo 1 and 2. c2 = unnamed, photos 3, 4 AND the
    # Personal photo 5 - majority Communal, so it IS queued, but photo 5 must
    # never be shown. c3 = unnamed, only in the video. c4 = Personal friend.
    box = "100,80,260,260"
    write(os.path.join(d, "FACE-CLUSTERS.csv"), ["hash", "face_index", "cluster", "det_score", "bbox"],
          [[h(1), "0", "c1", "0.9", box], [h(2), "0", "c1", "0.9", box],
           [h(3), "0", "c2", "0.9", box], [h(4), "0", "c2", "0.8", box],
           [h(5), "0", "c2", "0.99", box], [h(5), "1", "c4", "0.9", box]])
    write(os.path.join(d, "FACE-CLUSTERS-VIDEO.csv"),
          ["hash", "image", "face_index", "cluster", "det_score", "bbox", "how"],
          [[h(6), h(6) + "_t1000", "0", "c3", "0.9", box, "new"],
           [h(6), h(6) + "_t2000", "0", "c3", "0.9", box, "new"]])
    write(os.path.join(d, "CLUSTER-MERGES.csv"), ["cluster", "group", "person", "source"], [])
    write(os.path.join(d, "answers.csv"),
          ["when", "scope", "target", "field", "value", "confidence", "who", "note"],
          [["2026-09-01T10:00:00", "cluster", "c1", "person", "Asha Raja", "1.00", "krish", ""],
           ["2026-09-01T10:00:00", "cluster", "c4", "person", "Personal Friend", "1.00", "krish", ""]])
    write(os.path.join(d, "content_tags.csv"), ["hash", "tag", "value", "source", "confidence", "when"],
          [[h(1), "cluster", c, "faces", "1", "x"] for c in ("c1", "c2", "c3", "c4")])
    # c2's embedding is close to Asha's (c1): it should be suggested
    write(os.path.join(d, "faces.0.csv"), ["hash", "face_index", "bbox", "det_score", "said", "emb"],
          [[h(1), "0", box, "0.9", "", emb(1)], [h(2), "0", box, "0.9", "", emb(1)],
           [h(3), "0", box, "0.9", "", emb(1)], [h(4), "0", box, "0.9", "", emb(1)]])
    write(os.path.join(d, "faces.video.csv"), ["hash", "image", "face_index", "bbox", "det_score", "emb"], [])
    os.makedirs(os.path.join(d, "thumbs"), exist_ok=True)
    os.makedirs(os.path.join(d, "frames"), exist_ok=True)
    return SimpleNamespace(
        db=os.path.join(d, "library.db"), assign=os.path.join(d, "FACE-CLUSTERS.csv"),
        video_assign=os.path.join(d, "FACE-CLUSTERS-VIDEO.csv"),
        merges=os.path.join(d, "CLUSTER-MERGES.csv"), answers=os.path.join(d, "answers.csv"),
        tags=os.path.join(d, "content_tags.csv"), faces=os.path.join(d, "faces.0.csv"),
        video_faces=os.path.join(d, "faces.video.csv"), vectors=os.path.join(d, "none"),
        events=os.path.join(d, "none.json"), mirror=os.path.join(d, "none.csv"),
        thumbs=os.path.join(d, "thumbs"), frames=os.path.join(d, "frames"),
        frame_verdicts=os.path.join(d, "verdicts.csv"), max_queue=50)


def run(a):
    import blocklist
    orig = blocklist.blocked_hashes
    SI.blocked_hashes = lambda *x: set()
    try:
        return SI.build(a, size_of=lambda p: (512, 384), log=lambda *x: None)
    finally:
        SI.blocked_hashes = orig


def main():
    d = tempfile.mkdtemp()
    a = fixture(d)
    b = run(a)
    shown = {f["hash"] for f in b["faces"]}

    print("1. nothing Personal goes up")
    check("the Personal photo is not a photo row", h(5) in {p["hash"] for p in b["photos"]}, False)
    check("the mostly-Communal group IS queued", "c2" in {q["group_id"] for q in b["queue"]}, True)
    check("...but its Personal photo is never one of its faces", h(5) in shown, False)
    check("the Personal-only person is not in the people list",
          "Personal Friend" in {p["name"] for p in b["people"]}, False)
    check("the family member is", [p["name"] for p in b["people"]], ["Asha Raja"])
    check("a path is sent relative to ContentLibrary, as Drive has it",
          sorted(p["rel_path"] for p in b["photos"])[0], "Media/Communal/2014/a.jpg")
    check("bboxes are sent as fractions of the image they were measured on",
          b["faces"][0]["bbox"], [round(100 / 512, 5), round(80 / 384, 5), round(260 / 512, 5), round(260 / 384, 5)])

    print()
    print("2. a video face needs its own frame's verdict")
    check("with no verdict, the video-only group is not asked",
          "c3" in {q["group_id"] for q in b["queue"]}, False)
    write(a.frame_verdicts, ["key", "nudity", "subject_age", "sexual", "note"],
          [[h(6) + ":" + h(6) + "_t1000:0", "full", "adult", "no", ""]])
    check("an adult-nudity frame verdict keeps it out",
          "c3" in {q["group_id"] for q in run(a)["queue"]}, False)
    write(a.frame_verdicts, ["key", "nudity", "subject_age", "sexual", "note"],
          [[h(6) + ":" + h(6) + "_t1000:0", "none", "adult", "no", ""]])
    b2 = run(a)
    check("a cleared frame lets the group be asked",
          "c3" in {q["group_id"] for q in b2["queue"]}, True)
    check("...using ONLY the cleared frame",
          sorted(f["key"] for f in b2["faces"] if f["frame"]),
          [h(6) + ":" + h(6) + "_t1000:0"])
    check("and that frame is the one uploaded",
          list(b2["_frames"]), ["frames/{}_{}_t1000.jpg".format(h(6), h(6))])

    print()
    print("3. suggestions are joined by key")
    q = {x["group_id"]: x for x in b["queue"]}["c2"]
    check("the named look-alike is suggested", [s["name"] for s in q.get("suggestions", [])], ["Asha Raja"])
    check("with a face from a shared photograph",
          q["suggestions"][0]["face"].split(":")[0] in {h(1), h(2)}, True)

    print()
    print("4. one tap for a whole day is one journal row per photograph")
    ans = [{"id": "u1", "scope": "file", "target": "x", "field": "place", "value": "Goa",
            "who": "grandma", "hashes": ["x", "y", "z"]},
           {"id": "u2", "scope": "cluster", "target": "c2", "field": "person",
            "value": "Kamala Raja", "who": "grandpa", "hashes": []}]
    rows = PA.expand(ans)
    check("three rows for three photographs, one for a face",
          [(r["id"], r["scope"], r["target"]) for r in rows],
          [("app-u1-0", "file", "x"), ("app-u1-1", "file", "y"),
           ("app-u1-2", "file", "z"), ("app-u2", "cluster", "c2")])
    check("each under the relative who said it", {r["who"] for r in rows}, {"grandma", "grandpa"})
    st = {"app-u1-0": {"status": "ingested", "reason": ""},
          "app-u1-1": {"status": "refused", "reason": "that photograph is not in the share set"},
          "app-u1-2": {"status": "ingested", "reason": ""},
          "app-u2": {"status": "ingested", "reason": ""}}
    v = PA.verdicts(ans, st)
    check("one refused photo makes the cloud row refused, with the reason",
          v["u1"], ("refused", "that photograph is not in the share set"))
    check("the face answer is ingested", v["u2"], ("ingested", None))

    print()
    print("5. a crash between recording and marking is finished next time")
    check("rows the ingest skipped as already done are marked from the cursor",
          PA.verdicts(ans[1:], {}, {"app-u2"}), {"u2": ("ingested", None)})
    check("a row neither reported nor in the cursor is left alone",
          PA.verdicts(ans[1:], {}, set()), {})

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
