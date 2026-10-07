r"""The cloud worker builds the family app's index from Drive alone, safely.

    python tests\test_app_cloud.py          # needs a Postgres: TEST_PG_DSN

stages/13_app/cloud_enrich.py is the ONE writer of the index and runs
unattended in a PUBLIC GitHub Actions log. Pinned here against a real Postgres
with the app's real migrations, with Drive, Gemini and the face model faked so
every verdict is known in advance:

  1. adult nudity, a screenshot and a refused judgement are HELD; the baby in
     the bath is shared (the same rule as the seed and the web app)
  2. faces cluster by person; a weak face starts nothing
  3. a second run with nothing new changes nothing
  4. the spend cap stops new work, and so does the deadline - and both
     still group, rebuild and write the receipt
  5. a file deleted from Drive leaves; a broken listing removes nothing
  6. two clusters with different NAMES are never merged, and a name given to
     one cluster still names its group after a merge
  7. a cluster id is never reissued, even when the counter was lost (l. 72)
  8. the library, once (LIBRARY-EXPORT.md): bound by md5 and paid for only
     where the library never looked; held wins every tie and holds a purged
     file that turns up later; a changed file is judged afresh; the library's
     groups are pinned; "needs identifying" asks first; a turned thumbnail's
     box and a video face are never drawn; a file that leaves Drive keeps what
     the library knew and re-binds when it returns; one import per file
  9. NOTHING but numbers reaches stdout: no path, no name, no description

A database test that cannot reach its database FAILS - a green run with
Postgres down once reported six tests as passing that had not run.
"""

import contextlib
import io
import json
import os
import shutil
import sqlite3
import struct
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

import numpy as np                                               # noqa: E402
import cloud_enrich as CE                                        # noqa: E402

FAILURES = []
DSN = os.environ.get("TEST_PG_DSN", "postgresql://postgres:pw@127.0.0.1:54329/postgres")
NAME = "arch_cloud_test"


def check(name, got, want):
    ok = got == want
    print("  {:<62} {}".format(name, "OK" if ok else "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def unit(seed, base=None, noise=0.0):
    r = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    r = r / np.linalg.norm(r)
    v = r if base is None else base + noise * r       # noise as a fraction of the face itself
    return v / np.linalg.norm(v)


A, B = unit(1), unit(2)

# id -> (relative path, mime, verdict, faces[(emb, det, share)])
OK = {"kind": "photo", "sensitivity": "none", "nudity": "none", "subject_age": "adult", "sexual": "no",
      "description": "Grandma Secretname at the beach with a red umbrella.", "occasion": "holiday"}
FILES = {
    "f1": ("Media/Communal/2001/secret-one.jpg", "image/jpeg", OK, [(unit(11, A, .25), .9, .3)]),
    "f2": ("Media/Communal/2001/secret-two.jpg", "image/jpeg", OK, [(unit(12, A, .25), .9, .3)]),
    "f3": ("Media/Communal/2002/secret-nude.jpg", "image/jpeg",
           dict(OK, nudity="full", subject_age="adult"), []),
    "f4": ("Media/Communal/2003/secret-bath.jpg", "image/jpeg",
           dict(OK, sensitivity="private-family", nudity="full", subject_age="child"), []),
    "f5": ("Media/Communal/2004/secret-screen.png", "image/png", dict(OK, kind="screenshot"), []),
    "f6": ("Media/Communal/2005/secret-six.jpg", "image/jpeg", OK,
           [(unit(13, B, .25), .9, .3), (unit(99), .4, .05)]),        # a weak stranger in the back
    "f7": ("Media/Communal/2005/secret-seven.jpg", "image/jpeg", OK, [(unit(14, B, .25), .9, .3)]),
    "f8": ("Media/Communal/2006/secret-vid.mp4", "video/mp4", dict(OK, kind="photo"), [(unit(15, A, .25), .9, .3)]),
    "f9": ("Media/Communal/2007/secret-blocked.jpg", "image/jpeg", None, []),
}


class FakeDrive:
    def __init__(self, ids):
        self.ids = ids

    def list_tree(self, root, prefix):
        return [{"id": i, "rel": FILES[i][0], "mime": FILES[i][1], "md5": "m" + i,
                 "time": "2001:06:0{} 12:00:00".format(len(i)), "lat": None, "lon": None,
                 "w": 1024, "h": 768} for i in self.ids]

    def image(self, fid, px):
        return ("JPEG:" + fid).encode()


class FakeGemini:
    def __init__(self, cost=0.001):
        self.cost, self.calls = cost, 0

    def classify(self, jpeg):
        self.calls += 1
        v = FILES[jpeg.decode().split(":")[1]][2]
        if v is None:
            raise RuntimeError("BLOCKED: no text, finishReason SAFETY")
        return dict(v), self.cost

    def embed(self, text):
        return [0.01] * 768, 0.0


class FakeFaces:
    def detect(self, jpeg):
        return [{"bbox": [0.3, 0.2, 0.6, 0.6], "det": d, "emb": e, "share": s}
                for e, d, s in FILES[jpeg.decode().split(":")[1]][3]]


def fresh_db(name=NAME):
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute("drop database if exists {} with (force)".format(name))
        admin.execute("create database {}".format(name))
    db = psycopg.connect(DSN.rsplit("/", 1)[0] + "/" + name, prepare_threshold=None)
    base = os.path.join(ROOT, "web", "supabase")
    db.execute(open(os.path.join(base, "test", "shim.sql")).read())
    for m in sorted(os.listdir(os.path.join(base, "migrations"))):
        db.execute(open(os.path.join(base, "migrations", m)).read())
    db.commit()
    return db


def run(db, ids, out, **kw):
    w = CE.Worker(db, FakeDrive(ids), kw.pop("gemini", FakeGemini()), FakeFaces(), None,
                  "root", "Media/Communal", workers=1, **kw)
    with contextlib.redirect_stdout(out):
        return w.run()


def q(db, sql, *a):
    return db.execute(sql, a).fetchall()


def main():
    try:
        db = fresh_db()
    except Exception as e:                                       # noqa: BLE001
        print("FAILED: no Postgres for this test ({}). Set TEST_PG_DSN.".format(type(e).__name__))
        return 2
    out = io.StringIO()
    allids = list(FILES)

    print("1. the publication rule")
    r = run(db, allids, out, budget=100)
    held = dict(q(db, "select drive_id, reason from held"))
    check("adult nudity is held", "f3" in held, True)
    check("a screenshot is held", "f5" in held, True)
    check("a file the classifier refused to judge is held", "f9" in held, True)
    shown = {x[0] for x in q(db, "select drive_id from photos")}
    check("the baby in the bath is shared", "f4" in shown, True)
    check("ordinary photos and the video are shared", {"f1", "f2", "f6", "f7", "f8"} <= shown, True)
    check("shared + held = everything listed", len(shown) + len(held), len(FILES))

    print()
    print("2. faces cluster by person")
    cl = dict(q(db, "select hash, cluster_id from faces"))
    check("A's three faces share one cluster",
          len({cl["drive:f1"], cl["drive:f2"], cl["drive:f8"]}), 1)
    check("B is a different cluster", cl["drive:f6"] != cl["drive:f1"], True)
    check("the weak background face started nothing",
          q(db, "select count(*) from faces where hash = 'drive:f6'")[0][0], 1)
    queue = {x[0] for x in q(db, "select group_id from queue")}
    check("both people are in the naming queue", len(queue), 2)

    print()
    print("3. a second run with nothing new changes nothing")
    g = FakeGemini()
    r2 = run(db, allids, out, budget=100, gemini=g)
    check("nothing classified, added, held or removed",
          (g.calls, r2.get("added", 0), r2.get("held", 0), r2.get("removed", 0)), (0, 0, 0, 0))

    print()
    print("4. the spend cap stops new work")
    db2 = fresh_db(NAME + "_cap")
    g = FakeGemini(cost=1.0)
    r3 = run(db2, allids, io.StringIO(), budget=100, cap_usd=2.5, gemini=g)
    # one worker keeps two files queued: the 3rd crosses $2.50, the 4th was
    # already in flight, and nothing after it starts
    check("it stopped after the cap (3 to cross it + 1 in flight)", g.calls, 4)
    check("and says so", r3.get("cap_reached"), 1)
    db2.close()
    db3 = fresh_db(NAME + "_time")
    g = FakeGemini()
    r5 = run(db3, allids, io.StringIO(), budget=100, max_minutes=0, gemini=g)
    check("past the deadline nothing new starts (2 already in flight)", g.calls, 2)
    check("and says so", r5.get("time_up"), 1)
    check("it still wrote its receipt",
          q(db3, "select count(*) from snapshots where kind = 'drive-sync'")[0][0], 1)
    db3.close()

    print()
    print("5. deletions follow Drive; a broken listing removes nothing")
    r4 = run(db, [i for i in allids if i != "f7"], out, budget=100)
    check("the deleted file left the index", r4.get("removed"), 1)
    check("its face went with it", q(db, "select count(*) from faces where hash = 'drive:f7'")[0][0], 0)
    run(db, [], out, budget=100)
    check("an empty listing removed nothing",
          q(db, "select count(*) from photos")[0][0], len(shown) - 1)

    print()
    print("6. names: never merged across, never detached")
    w = CE.Worker(db, None, None, None, None, "", "")
    db.execute("insert into clusters (cluster_id, group_id, centroid, n) values "
               "('x1','x1',%s::extensions.vector,5), ('x2','x2',%s::extensions.vector,4), "
               "('x3','x3',%s::extensions.vector,3)",
               (CE.vec(unit(30)), CE.vec(unit(31, unit(30), .05)), CE.vec(unit(32, unit(30), .05))))
    for t, v in (("x1", "Asha Secretname"), ("x2", "Meera Secretname")):
        db.execute("insert into answers (id, who, scope, target, field, value) values "
                   "(gen_random_uuid(), 'krish', 'cluster', %s, 'person', %s)", (t, v))
    db.commit()
    with contextlib.redirect_stdout(out):
        w.group()
    grp = dict(q(db, "select cluster_id, group_id from clusters where cluster_id like 'x%%'"))
    check("two differently-named look-alikes stay two people", grp["x1"] != grp["x2"], True)
    check("the unnamed look-alike joins one of them", grp["x3"] in (grp["x1"], grp["x2"]), True)
    names = dict(q(db, "select group_id, name from group_names"))
    check("the merged group still carries the name given to its cluster",
          names[grp["x3"]] in ("Asha Secretname", "Meera Secretname"), True)

    print()
    print("7. a cluster id is never reissued")
    db.execute("delete from sync_state where key = 'next_cluster'")
    db.commit()
    w = CE.Worker(db, None, None, None, None, "", "")
    w.load_clusters()
    top = max(int(c[1:]) for (c,) in q(db, "select cluster_id from clusters where cluster_id ~ '^k[0-9]+$'"))
    check("with the counter lost, the next id still clears every k-id", w.next_id > top, True)

    print()
    print("8. the library, once")
    library(out)

    print()
    print("8c. the owner's private places, periods and people")
    private_rules(out)

    print()
    print("8d. a video plays only once the whole of it has been judged")
    videos(out)

    print()
    print("8e. the owner's Personal folder: in when someone he chose is clearly in it")
    personal(out)

    print()
    print("8b. a rate limit waits and tries again; a refusal does not")
    class FakeCL:
        def __init__(self, fails, code):
            self.fails, self.code, self.calls = fails, code, 0

        def call(self, paths, key, prompt, max_out):
            self.calls += 1
            if self.calls <= self.fails:
                raise RuntimeError("HTTP {}: no".format(self.code))
            return "{}", 10, 2
    import threading
    gm = CE.Gemini.__new__(CE.Gemini)
    gm.key, gm.gate, gm.backoff = "k", threading.Semaphore(2), 0.001
    gm.CL = FakeCL(2, 429)
    try:
        got = gm._call(["x"], "p", 10)
    except RuntimeError:
        got = "gave up"
    check("two rate limits, then an answer", (got, gm.CL.calls), (("{}", 10, 2), 3))
    gm.CL = FakeCL(1, 400)
    try:
        gm._call(["x"], "p", 10)
        check("a refusal (400) is not retried", "retried", "raised")
    except RuntimeError:
        check("a refusal (400) is not retried", gm.CL.calls, 1)
    check("the log names an error by its status, never its message",
          (CE.err_name(RuntimeError("HTTP 429: secret-path.jpg")), CE.err_name(ValueError("secret"))),
          ("http_429", "ValueError"))

    print()
    print("9. the public log carries numbers only")
    text = out.getvalue()
    leaks = [s for s in ("secret", "Secretname", "beach", "umbrella", "Media/Communal", ".jpg")
             if s.lower() in text.lower()]
    check("no path, name or description reached stdout", leaks, [])
    try:
        CE.say("listed", path="Media/Communal/x.jpg")
        check("say() refuses a string", "accepted", "refused")
    except TypeError:
        check("say() refuses a string", "refused", "refused")

    db.close()
    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


# ------------------------------------------------------------- the library --

def blob(v, dim):
    v = np.asarray(v, dtype=np.float32)
    assert v.shape == (dim,)
    return struct.pack("<{}f".format(dim), *(v / np.linalg.norm(v)).tolist())


def desc(seed):
    return np.random.default_rng(seed).normal(size=768).astype(np.float32)


def write_bundle(path, broken=False):
    """A small library export, written with the WRITER's own schema."""
    import export_library as EL
    L = "Media/Communal/1998/"
    db = sqlite3.connect(path)
    db.executescript(EL.SCHEMA)
    photos = [  # hash, md5, rel, media, people
        ("b1", "m-l1", L + "secret-l1.jpg", "photo", ["Asha Secretname"]),
        ("b2", "m-l2", L + "secret-l2.jpg", "photo", []),
        ("b3", "m-l3", L + "secret-l3.jpg", "photo", []),
        ("b4", "m-l4", L + "secret-l4.jpg", "photo", []),       # not on Drive yet
        ("b5", None, L + "secret-l5.jpg", "photo", ["Dev Secretname"]),  # md5 unknown: by path
        ("b6", "m-l6-old", L + "secret-l6.jpg", "photo", []),   # Drive's file changed since
        ("b7", "m-l7", L + "secret-l7.jpg", "photo", []),       # the cloud judged it first
        ("b8", "m-l8", L + "secret-l8.mp4", "video", []),
    ]
    for i, (h, md5, rel, media, people) in enumerate(photos):
        db.execute("insert into photos (hash, md5, rel_path, media, year, description, people, embedding) "
                   "values (?,?,?,?,?,?,?,?)", (h, md5, rel, media, 1998,
                                                  "Secretname family at the beach", json.dumps(people),
                                                  blob(desc(100 + i), 768)))
    db.execute("insert into held values ('bh1', 'm-h1', ?, 'nudity')", (L + "secret-h1.jpg",))
    db.execute("insert into held values ('bh2', 'm-h2', NULL, 'removed')")   # purged: md5 only
    C1, C3 = unit(40), unit(41)
    clusters = {"c1": "g1", "c2": "g1",      # people merged these two, though the faces differ
                "c3": "g3", "c4": "g4",      # people kept these apart, though the faces are alike
                "c5": "g5",      # someone seen only in a video
                "c6": "g6",      # unnamed, and in MORE photos than the face the library flagged
                "c7": "g7",      # flagged, seen only in a video: its frame is clean
                "c8": "g8",      # flagged, video only: its best frame is not clean, its next one is
                "c9": "g9",      # flagged, video only: the person is not found in the frame
                "c10": "g10"}    # flagged, video only: the frame's judgement is rate-limited once
    for c, g in clusters.items():
        db.execute("insert into clusters values (?, ?)", (c, g))
    faces = [  # key, hash, image, idx, cluster, box, thumb, share, only, emb
        ("b1::0", "b1", "", 0, "c1", (.3, .2, .6, .6), (400, 300), .3, 1, unit(50, C1, .2)),
        ("b3::0", "b3", "", 0, "c1", (.3, .2, .6, .6), (400, 300), .3, 1, unit(51, C1, .2)),
        ("b2::0", "b2", "", 0, "c2", (.3, .2, .6, .6), (300, 400), .3, 1, unit(52)),   # thumb turned
        ("b2::1", "b2", "", 1, "c3", None, None, None, 0, unit(53, C3, .2)),           # no thumbnail
        ("b5::0", "b5", "", 0, "c3", (.3, .2, .6, .6), (400, 300), .3, 1, unit(54, C3, .2)),
        ("b6::0", "b6", "", 0, "c3", (.3, .2, .6, .6), (400, 300), .3, 1, unit(55, C3, .2)),
        ("b7::0", "b7", "", 0, "c4", (.3, .2, .6, .6), (400, 300), .3, 1, unit(56, C3, .2)),
        ("b8:b8_t1000:0", "b8", "b8_t1000", 0, "c5", None, None, None, 1, unit(57)),               # video
        ("b8:b8_t2000:0", "b8", "b8_t2000", 0, "c5", None, None, None, 1, unit(58, unit(57), .2)),
        ("b8:b8_t3000:0", "b8", "b8_t3000", 0, "c7", None, None, None, 1, unit(70)),
        ("b8:b8_t5000:0", "b8", "b8_t5000", 0, "c8", None, None, None, 1, unit(71)),
        ("b8:b8_t6000:0", "b8", "b8_t6000", 0, "c8", None, None, None, 1, unit(72, unit(71), .2)),
        ("b8:b8_t7000:0", "b8", "b8_t7000", 0, "c9", None, None, None, 1, unit(73)),
        ("b8:b8_t8000:0", "b8", "b8_t8000", 0, "c10", None, None, None, 1, unit(74)),
        ("b8::0", "b8", "", 0, "c5", (.3, .2, .6, .6), (400, 300), .3, 1, unit(63, unit(57), .2)),  # library's own frame grab
        ("b1::1", "b1", "", 1, "c6", (.6, .2, .9, .6), (400, 300), .3, 0, unit(60, unit(59), .2)),
        ("b3::1", "b3", "", 1, "c6", (.6, .2, .9, .6), (400, 300), .3, 0, unit(61, unit(59), .2)),
        ("b7::1", "b7", "", 1, "c6", (.6, .2, .9, .6), (400, 300), .3, 0, unit(62, unit(59), .2)),
    ]
    for key, h, img, idx, c, box, th, share, only, emb in faces:
        x1, y1, x2, y2 = box or (None,) * 4
        tw, thh = th or (None, None)
        det = .95 if key.endswith("t5000:0") else .9       # c8's held frame is its best face
        db.execute("insert into faces values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (key, h, img, idx, c, x1, y1, x2, y2, tw, thh, det, share, only, blob(emb, 512)))
    journal = [  # when, who, scope, target, field, value
        ("2026-09-01T10:00:00", "krish", "cluster", "c1", "person", "Asha Secretname"),
        ("2026-09-02T10:00:00", "krish", "cluster", "c3", "unidentifiable", "declined"),
        ("2026-09-03T10:00:00", "krish", "cluster", "c3", "needs_identifying", "Bharti"),
        ("2026-09-02T10:00:00", "krish", "cluster", "c4", "needs_identifying", "Bharti"),
        ("2026-09-04T10:00:00", "bharti", "cluster", "c4", "person", "Meera Secretname"),
        ("2026-09-05T10:00:00", "krish", "file", "b1", "place", "Secretville"),
        ("2026-09-06T10:00:00", "krish", "cluster", "c5", "person", "Ravi Secretname"),
        ("2026-09-07T10:00:00", "krish", "cluster", "c7", "needs_identifying", "Bharti"),
        ("2026-09-07T10:00:00", "krish", "cluster", "c8", "needs_identifying", "Bharti"),
        ("2026-09-07T10:00:00", "krish", "cluster", "c9", "needs_identifying", "Bharti"),
        ("2026-09-07T10:00:00", "krish", "cluster", "c10", "needs_identifying", "Bharti"),
    ]
    for w, who, sc, t, f, v in journal:
        aid = str(uuid.uuid5(uuid.NAMESPACE_URL, "journal:" + "|".join((w, who, sc, t, f, v))))
        db.execute("insert into answers values (?,?,?,?,?,?,?,?,?)", (aid, w, who, sc, t, f, v, 1.0, ""))
    counts = {t: db.execute("select count(*) from " + t).fetchone()[0]
              for t in ("photos", "held", "clusters", "faces", "answers")}
    if broken:
        counts["faces"] += 1
    db.execute("insert into meta values ('format', '1')")
    db.execute("insert into meta values ('counts', ?)", (json.dumps(counts),))
    db.commit()
    db.close()
    return counts


CLEAN = {"nudity": "none", "subject_age": "adult", "sexual": "no"}
FRAME_SPEC = {}     # the JPEG bytes of a fake frame -> what is in it


def fake_jpeg(seed):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), ((seed * 37) % 256, (seed * 91) % 256, (seed * 13) % 256)).save(buf, "JPEG")
    return buf.getvalue()


class LibDrive:
    """Drive with the export shared with the account (or not yet)."""
    L = "Media/Communal/1998/"

    def __init__(self, bundle=None):
        self.bundle, self.files, self.frames_asked = bundle, {}, []
        same = lambda v: [{"bbox": [.2, .2, .5, .6], "det": .9, "emb": v, "share": .3}]   # noqa: E731
        stranger = [{"bbox": [.2, .2, .5, .6], "det": .9, "emb": unit(999), "share": .3}]
        self.video = {   # (file, ms) -> (faces in the frame, its verdict)
            ("d8", 1000): (same(unit(57)), CLEAN),
            ("d8", 3000): (same(unit(70)), CLEAN),
            ("d8", 5000): (same(unit(71)), {"nudity": "full", "subject_age": "adult", "sexual": "no"}),
            ("d8", 6000): (same(unit(72, unit(71), .2)), CLEAN),
            ("d8", 7000): (stranger, CLEAN),
            ("d8", 8000): (same(unit(74)), "RATE LIMITED ONCE"),
        }

    def frame(self, fid, ms, px=960):
        self.frames_asked.append((fid, ms))
        if (fid, ms) not in self.video:
            return None
        jpeg = fake_jpeg(ms)
        FRAME_SPEC[jpeg] = self.video[(fid, ms)]
        return jpeg

    def put(self, fid, md5, rel, mime="image/jpeg", w=1024, h=768, rot=0):
        self.files[fid] = {"id": fid, "rel": rel, "mime": mime, "md5": md5, "time": None,
                           "lat": None, "lon": None, "w": w, "h": h, "rot": rot}

    def list_tree(self, root, prefix):
        return list(self.files.values())

    def image(self, fid, px):
        return ("JPEG:" + fid).encode()

    def find(self, name):
        if not self.bundle:
            return None
        import hashlib
        return {"id": "bundle", "md5Checksum": hashlib.md5(open(self.bundle, "rb").read()).hexdigest()}

    def download(self, fid, dest, md5=None):
        shutil.copyfile(self.bundle, dest)


class LibFaces:
    def detect(self, jpeg):
        return FRAME_SPEC.get(jpeg, ([], None))[0]


class LibGemini:
    def __init__(self):
        self.seen, self.frames_judged = [], 0

    limited = set()

    def sensitivity(self, jpeg):
        self.frames_judged += 1
        v = FRAME_SPEC[jpeg][1]
        if v == "RATE LIMITED ONCE":
            if jpeg not in LibGemini.limited:
                LibGemini.limited.add(jpeg)
                raise RuntimeError("HTTP 429: Resource has been exhausted")
            v = CLEAN
        return dict(v), 0.0002

    def classify(self, jpeg):
        self.seen.append(jpeg.decode().split(":")[1])
        return dict(OK), 0.001

    def embed(self, text):
        return [0.01] * 768, 0.0


def private_rules(out):
    """Made-up names and places only: the real rules never enter this public
    repository (migration 0008)."""
    db = fresh_db(NAME + "_priv")
    rows = [  # hash, place, country, taken_at, people, description
        ("p1", "Secretbay", "Farland", "2023-05-01", ["Owner", "Partner"], "two people on a beach"),
        ("p2", "Secretbay", "Farland", "2023-05-02", ["Owner", "Aunt Secretname"], "lunch"),
        ("p3", "Secretbay Beach", "Farland", "2023-05-03", [], "the sea"),
        ("p4", "Elsewhere", "Farland", "2023-06-01", [], "a street"),
        ("p5", "Homeplace", "Homeland", "2023-06-01", [], "a garden"),
        ("p6", None, None, "2023-07-01", ["Owner"], "a room"),
        ("p7", "Homeplace", "Homeland", "2019-01-01", ["Partner"], "a cafe"),
        ("p8", "Homeplace", "Homeland", "2019-01-02", ["Partner", "Aunt Secretname"], "a birthday"),
        ("p9", "Homeplace", "Homeland", "2018-01-01", ["Owner"], "a picnic, a kite and a lantern"),
        ("p10", "Homeplace", "Homeland", "2018-02-01", ["Aunt Secretname"], "a picnic"),
        ("p11", "Homeplace", "Homeland", "2017-01-01", [], "hidden by a person"),
        ("p12", "Allowtown Park", "Homeland", "2019-03-01", ["Partner"], "a park"),
        ("p13", "Secretbay", "Farland", "2023-05-04", ["Owner", "Friend Onlyhere"], "drinks"),
    ]
    for h, place, country, at, people, desc in rows:
        db.execute("insert into photos (hash, drive_id, place, country, taken_at, people, description) "
                   "values (%s, %s, %s, %s, %s, %s, %s)", (h, "d" + h, place, country, at, people, desc))
    db.execute("update photos set hidden = true, hidden_by = 'grandma' where hash = 'p11'")
    for r in ("('ignore', null, null, null, null, false, 'Owner')", "('ignore', null, null, null, null, false, 'Partner')",
              "('place', 'secretbay', null, null, null, false, null)",
              "('period', null, '2023-06-01', '2023-08-01', array['Farland'], true, null)",
              "('person', null, null, null, null, false, 'Partner')",
              "('words', 'picnic|kite|lantern', null, null, null, false, null)"):
        db.execute("insert into private_rules (kind, pattern, from_at, to_at, countries, unplaced, name) values " + r)
    db.execute("insert into private_overrides (kind, pattern, n) values ('allow', 'allowtown', null), ('family_min', null, 2)")
    db.commit()
    dry = q(db, "select * from apply_private_rules(true)")[0]
    check("a dry run counts and changes nothing",
          (dry[0], q(db, "select count(*) from photos where hidden_by = 'rule:private'")[0][0]), (7, 0))
    w = CE.Worker(db, None, None, None, None, "", "")
    with contextlib.redirect_stdout(out):
        w.private()
    shown = {h for (h,) in q(db, "select hash from photos where visible")}
    check("a private place hides the owner and partner, and nobody recognised", ("p1" in shown, "p3" in shown), (False, False))
    check("someone else in the family keeps a photograph shown", ("p2" in shown, "p8" in shown, "p10" in shown), (True, True, True))
    check("a private period hides its country and the unplaced, not another country",
          ("p4" in shown, "p6" in shown, "p5" in shown), (False, False, True))
    check("the partner alone, anywhere, is private", "p7" in shown, False)
    check("private words with only the owner are private", "p9" in shown, False)
    check("a place that is always fine overrides every rule", "p12" in shown, True)
    check("a friend seen only inside the private places is not family", "p13" in shown, False)
    check("a photograph a person hid stays theirs", q(db, "select hidden_by from photos where hash = 'p11'")[0][0], "grandma")
    again = q(db, "select * from apply_private_rules()")[0]
    check("a second run changes nothing", (again[0], again[1]), (0, 0))
    # a place the family types can bring a photograph INTO a private place, never take one out
    db.execute("update photos set family_place = 'Secretbay Pier' where hash = 'p5'")
    db.execute("update photos set family_place = 'Allowtown Park' where hash = 'p1'")
    db.commit()
    q(db, "select * from apply_private_rules()")
    shown = {h for (h,) in q(db, "select hash from photos where visible")}
    check("a family's place can make a photograph private, never public again",
          ("p5" in shown, "p1" in shown), (False, False))
    db.execute("update photos set family_place = null where hash in ('p5', 'p1')")
    db.commit()
    q(db, "select * from apply_private_rules()")
    # who is in it: a family member taken off a photograph no longer keeps it shown
    db.execute("insert into answers (id, who, scope, target, field, value, hashes) values "
               "(gen_random_uuid(), 'gran', 'file', 'p2', 'not_in_photo', 'Aunt Secretname', array['p2'])")
    db.commit()
    q(db, "select * from apply_private_rules()")
    check("a name the family takes off a photograph no longer counts there",
          ("p2" in {h for (h,) in q(db, "select hash from photos where visible")},
           q(db, "select count(*) from photo_people where hash = 'p2' and name = 'Aunt Secretname'")[0][0]), (False, 0))
    db.execute("insert into answers (id, who, scope, target, field, value, hashes) values "
               "(gen_random_uuid(), 'dev', 'file', 'p2', 'in_photo', 'Aunt Secretname', array['p2']), "
               "(gen_random_uuid(), 'meera', 'file', 'p2', 'in_photo', 'aunt  secretname', array['p2'])")
    db.commit()
    q(db, "select * from apply_private_rules()")
    check("and two who say she is in it outvote one who said she is not",
          "p2" in {h for (h,) in q(db, "select hash from photos where visible")}, True)
    db.execute("delete from private_rules where kind = 'words'")
    db.commit()
    back = q(db, "select * from apply_private_rules()")[0]
    check("a rule taken away shows its photographs again", (back[1], "p9" in {h for (h,) in q(db, "select hash from photos where visible")}), (1, True))
    db.close()


def clip(path, seconds, codec="libx264"):
    """A real, tiny video for the probe and the remux to read."""
    import subprocess
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc=duration={}:size=160x120:rate=5".format(seconds),
                    "-f", "lavfi", "-i", "sine=duration={}".format(seconds),
                    "-c:v", codec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path],
                   check=True, capture_output=True)


class VidDrive:
    """fid -> (mime, size, the local clip it downloads as)."""
    def __init__(self, files):
        self.files, self.downloads, self.asked = files, [], []

    def meta(self, fid):
        self.asked.append(fid)
        mime, size, _ = self.files[fid]
        return {"mime": mime, "size": size}

    def download(self, fid, dest, md5=None):
        self.downloads.append(fid)
        shutil.copyfile(self.files[fid][2], dest)


class VidGemini:
    """What each video holds, by its length in seconds (the clips differ only in that)."""
    def __init__(self, by_len):
        self.by_len, self.watched, self.no_sound = by_len, [], []

    def video(self, path, seconds):
        n = int(round(seconds))
        self.watched.append(n)
        self.no_sound.append(CE.probe(path)["codec"] == "h264" and not _has_audio(path))
        v = self.by_len[n]
        if isinstance(v, list) and v and v[0] == "FAIL ONCE":
            if n not in getattr(self, "failed", set()):
                self.__dict__.setdefault("failed", set()).add(n)
                raise RuntimeError("HTTP 400: secret-video.mp4")
            v = v[1:]
        return [dict(x) for x in v], 0.003


def _has_audio(path):
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", path], capture_output=True)
    return bool(r.stdout.strip())


def videos(out):
    """A video plays only once the whole of it has been judged (Krish, 2026-10-06)."""
    db = fresh_db(NAME + "_vid")
    tmp = tempfile.mkdtemp()
    c = lambda n, codec="libx264", ext="mp4": (clip(os.path.join(tmp, "{}.{}".format(n, ext)), n, codec),   # noqa: E731
                                               os.path.join(tmp, "{}.{}".format(n, ext)))[1]
    adult = {"nudity": "partial", "subject_age": "adult", "sexual": "no", "nudity_note": "secret note"}
    files = {   # drive id -> (mime, size, clip); what the model sees in it is keyed by length
        "dv-ok": ("video/mp4", 1000, c(2)),
        "dv-nude": ("video/quicktime", 1000, c(3)),
        "dv-bath": ("video/quicktime", 1000, c(4, ext="mov")),
        "dv-mpg": ("video/mpeg", 1000, None),
        "dv-mp4v": ("video/mp4", 1000, c(5, "mpeg4")),
        "dv-big": ("video/mp4", 3_000_000_000, None),
        "dv-flaky": ("video/mp4", 1000, c(6)),
        "dv-blocked": ("video/mp4", 1000, c(7)),
        "dv-empty": ("video/mp4", 1000, c(8)),
        "dv-private": ("video/mp4", 1000, c(9)),
        "dv-vp9": ("video/mp4", 1000, c(10, "libvpx-vp9")),
    }
    gem = VidGemini({
        2: [CLEAN], 3: [CLEAN, adult], 4: [{"nudity": "partial", "subject_age": "child", "sexual": "no"}],
        6: ["FAIL ONCE", CLEAN], 7: [{"_blocked": True}], 8: [{}], 9: [CLEAN], 10: [CLEAN],
    })
    for fid in files:
        db.execute("insert into photos (hash, drive_id, media, people, taken_at) values (%s, %s, 'video', %s, %s)",
                   ("h" + fid, fid, ["Asha Secretname"] if fid == "dv-ok" else [], "2020-01-01"))
    db.execute("insert into photos (hash, drive_id, media) values ('h-photo', 'dp', 'photo')")
    db.execute("update photos set hidden = true, hidden_by = 'rule:private' where hash = 'hdv-private'")
    db.commit()
    drive = VidDrive(files)

    def go(n):
        w = CE.Worker(db, drive, gem, None, None, "", "", workers=2, videos=n)
        with contextlib.redirect_stdout(out):
            w.videos()
        return w

    go(0)
    check("no videos are judged unless asked (it is a spend)", (drive.asked, gem.watched), ([], []))
    w = go(1)
    check("a video with a named person in it is judged first", drive.downloads, ["dv-ok"])
    go(50)
    st = dict(q(db, "select drive_id, v.status from video_checks v join photos p using (hash)"))
    check("clear plays; adult nudity anywhere in it is held; a child in the bath plays",
          (st.get("dv-ok"), st.get("dv-nude"), st.get("dv-bath")), ("ok", "held", "ok"))
    check("a format no phone plays keeps its still and is never downloaded or judged",
          (st.get("dv-mpg"), st.get("dv-mp4v"), st.get("dv-big"), "dv-mpg" in drive.downloads,
           "dv-big" in drive.downloads, 5 in gem.watched), ("unplayable",) * 3 + (False, False, False))
    check("a refusal holds it; an unreadable answer is no verdict, so it is tried again",
          (st.get("dv-blocked"), st.get("dv-empty"), st.get("dv-flaky")), ("held", "error", "error"))
    check("a private video is never downloaded to be judged", ("dv-private" in drive.downloads, "dv-private" in st),
          (False, False))
    check("the model sees the picture alone, as H.264 it can decode, no sound",
          (all(gem.no_sound), 10 in gem.watched, st.get("dv-vp9")), (True, True, "ok"))
    hidden = dict(q(db, "select drive_id, hidden_by from photos where hidden"))
    check("a held video is hidden everywhere, still and all",
          (hidden.get("dv-nude"), hidden.get("dv-blocked"), hidden.get("dv-ok")),
          ("rule:video-check", "rule:video-check", None))
    check("what plays is told to the phone as MP4, a phone's QuickTime file included, with its length",
          q(db, "select drive_id, mime, seconds from video_checks v join photos p using (hash) "
                "where drive_id in ('dv-ok', 'dv-bath') order by drive_id"),
          [("dv-bath", "video/mp4", 4), ("dv-ok", "video/mp4", 2)])
    notes = q(db, "select count(*) from video_checks where verdict::text like '%%note%%'")[0][0]
    check("the stored verdict is category words only, never the model's note", notes, 0)
    check("the spend is counted", round(w.spent, 4) > 0 and q(db, "select sum(usd) > 0 from video_checks")[0][0], True)
    before = list(drive.downloads)
    go(50)
    st = dict(q(db, "select drive_id, v.status from video_checks v join photos p using (hash)"))
    check("the next run tries only the unjudged ones again, and judges nothing twice",
          (sorted(drive.downloads[len(before):]), st.get("dv-flaky")), (["dv-empty", "dv-flaky"], "ok"))
    go(50)
    go(50)
    check("an answer that never comes is tried three times, then left",
          (q(db, "select tries, status from video_checks v join photos p using (hash) where drive_id = 'dv-empty'"),
           drive.downloads.count("dv-empty")), ([(3, "error")], 3))
    check("a long tape is watched in parts that cover every second",
          (CE.segments(None), CE.segments(1200), CE.segments(3000.4)),
          ([(None, None)], [(None, None)], [(0, 1200), (1200, 2400), (2400, 3001)]))

    # the File API conversation itself, against a fake Google
    class R:
        def __init__(self, code=200, j=None, h=None):
            self.status_code, self._j, self.headers = code, j, h or {}

        def json(self):
            return self._j

    class Http:
        def __init__(self, gen_fails=False):
            self.log, self.polls = [], 0

        def post(self, url, **kw):
            self.log.append(("post", url, kw.get("headers", {})))
            if url.endswith("/upload/v1beta/files"):
                return R(h={"x-goog-upload-url": "https://up.example/abc"})
            return R(j={"file": {"name": "files/abc", "state": "PROCESSING"}})

        def get(self, url, **kw):
            self.log.append(("get", url, kw.get("headers", {})))
            self.polls += 1
            return R(j={"name": "files/abc", "state": "ACTIVE", "uri": "https://g.example/files/abc"})

        def delete(self, url, **kw):
            self.log.append(("delete", url, kw.get("headers", {})))
            return R()

    class GenCL:
        IN_PER_M, OUT_PER_M, SENS_PROMPT = 0.25, 1.5, "judge"
        parse = staticmethod(json.loads)

        def __init__(self, answers):
            self.answers, self.parts = list(answers), []

        def generate(self, parts, key, max_out, timeout):
            self.parts.append(parts[0])
            a = self.answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a, 1000, 10

    import threading
    gm = CE.Gemini.__new__(CE.Gemini)
    gm.key, gm.gate, gm.backoff, gm.poll = "SECRET-KEY", threading.Semaphore(1), 0.001, 0.001
    gm.http, gm.CL = Http(), GenCL(['{"nudity":"none"}'] * 3)
    v, usd = gm.video(files["dv-ok"][2], 2500)
    urls = [u for _, u, _ in gm.http.log]
    check("the video is uploaded once, waited for, watched in three parts, and deleted",
          ([m for m, _, _ in gm.http.log], [p.get("video_metadata") for p in gm.CL.parts], len(v)),
          (["post", "post", "get", "delete"],
           [{"start_offset": "0s", "end_offset": "1200s"}, {"start_offset": "1200s", "end_offset": "2400s"},
            {"start_offset": "2400s", "end_offset": "2500s"}], 3))
    check("the key travels in a header, never in an address", any("SECRET-KEY" in u for u in urls), False)
    gm.http, gm.CL = Http(), GenCL(['{"nudity":"none"}', RuntimeError("BLOCKED: no text"), '{"nudity":"none"}'])
    v, _ = gm.video(files["dv-ok"][2], 2500)
    check("a part the model refuses stops the watching and is held", (v[-1], len(v)), ({"_blocked": True}, 2))
    gm.http, gm.CL = Http(), GenCL([RuntimeError("HTTP 400: bad")])
    try:
        gm.video(files["dv-ok"][2], 60)
        check("an upload is deleted even when the look fails", "no error", "deleted")
    except RuntimeError:
        check("an upload is deleted even when the look fails", gm.http.log[-1][0], "delete")
    db.close()
    shutil.rmtree(tmp, ignore_errors=True)


class PersonalDrive:
    """Communal under 'root', the owner's Personal folder under 'proot'."""
    def __init__(self, communal, personal):
        self.communal, self.personal, self.seen = communal, personal, []

    def list_tree(self, root, prefix):
        src = self.communal if root == "root" else self.personal
        return [{"id": i, "rel": "{}/2019/secret-{}.jpg".format(prefix, i), "mime": "image/jpeg", "md5": "m" + i,
                 "time": "2019:06:01 12:00:00", "lat": None, "lon": None, "w": 1024, "h": 768} for i in src]

    def image(self, fid, px):
        self.seen.append(fid)
        return ("JPEG:" + fid).encode()

    def find(self, name):
        return None


def personal(out):
    """The owner's Personal folder: a photograph comes in when a person he
    ticked is clearly in it (Krish, 2026-10-06). Made-up names only."""
    db = fresh_db(NAME + "_pers")
    O, P, AU, CO = unit(201), unit(202), unit(203), unit(204)      # owner, partner, aunt, cousin
    for cid, name, v in (("c-o", "Owner", O), ("c-p", "Partner", P), ("c-a", "Aunt Secretname", AU),
                         ("c-c", "Cousin Secretname", CO)):
        db.execute("insert into clusters (cluster_id, group_id, name, centroid, n) "
                   "values (%s, %s, %s, %s::extensions.vector, 5)", (cid, cid, name, CE.vec(v)))
    for n in ("Owner", "Partner"):
        db.execute("insert into private_rules (kind, name) values ('ignore', %s)", (n,))
    db.execute("insert into personal_people (name) values ('Aunt Secretname')")
    db.commit()
    face = lambda base, seed, share=.3: (unit(seed, base, .25), .9, share)      # noqa: E731
    spec = {   # file -> (faces, what the classifier says)
        "c1": ([face(AU, 1)], OK),
        "pa": ([face(AU, 2)], OK),                                   # the aunt alone
        "pb": ([face(O, 3), face(P, 4)], OK),                        # the owner and partner
        "pc": ([face(O, 5), face(AU, 6)], OK),                       # the owner with the aunt
        "pd": ([face(AU, 7), (unit(777), .9, .3)], OK),              # the aunt and a stranger
        "pe": ([face(AU, 8), face(CO, 9)], OK),                      # the aunt and someone not ticked
        "pf": ([face(AU, 10, .03), face(O, 11)], OK),                # the aunt far in the back
        "pg": ([face(AU, 12)], dict(OK, nudity="partial", subject_age="adult")),
        "ph": ([face(O, 13)], OK),                                   # the owner alone
    }

    class Faces:
        def detect(self, jpeg):
            return [{"bbox": [.2, .2, .5, .6], "det": d, "emb": e, "share": s}
                    for e, d, s in spec[jpeg.decode().split(":")[1]][0]]

    class Gem:
        def __init__(self):
            self.seen = []

        def classify(self, jpeg):
            fid = jpeg.decode().split(":")[1]
            self.seen.append(fid)
            return dict(spec[fid][1]), 0.001

        def embed(self, text):
            return [0.01] * 768, 0.0

    drive = PersonalDrive(["c1"], ["pa", "pb", "pc", "pd", "pe", "pf", "pg", "ph"])

    def go(n=100):
        g = Gem()
        w = CE.Worker(db, drive, g, Faces(), None, "root", "Media/Communal", workers=2, budget=100, personal=n)
        with contextlib.redirect_stdout(out):
            w.run()
        return g

    def shown():
        return sorted(r[0] for r in q(db, "select drive_id from photos where visible and rel_path like 'Media/Personal/%%'"))

    g = go()
    check("before the folder is set up, nothing Personal is looked at",
          (sorted(set(drive.seen) - {"c1"}), q(db, "select count(*) from personal_seen")[0][0]), ([], 0))
    db.execute("insert into sync_state (key, value) values ('personal_folder', 'proot')")
    db.commit()
    clusters = q(db, "select count(*) from clusters")[0][0]
    g = go()
    check("in: the aunt alone, and with the owner; out: the owner alone, the two of them, the aunt far away",
          shown(), ["pa", "pc"])
    check("and with the switch on, out: a stranger beside her, or someone not ticked",
          ("pd" in shown(), "pe" in shown()), (False, False))
    check("only what qualifies is described (the spend)", sorted(g.seen), ["pa", "pc", "pg"])
    check("a Personal photo with adult nudity is held like any other",
          q(db, "select reason is not null from held where drive_id = 'pg'"), [(True,)])
    check("a Personal photo starts no new face for the family to name",
          q(db, "select count(*) from clusters")[0][0], clusters)
    g = go()
    check("a second run looks at nothing again and spends nothing", (g.seen, q(db, "select max(tries) from personal_seen")[0][0]),
          ([], 1))
    db.execute("insert into personal_people (name) values ('Cousin Secretname')")
    db.commit()
    go()
    check("ticking someone later brings their photographs in, without looking again",
          (shown(), q(db, "select max(tries) from personal_seen")[0][0]), (["pa", "pc", "pe"], 1))
    db.execute("insert into sync_state (key, value) values ('personal_strict', 'false')")
    db.commit()
    go()
    check("with the switch off, a stranger beside a ticked person no longer keeps it out", shown(),
          ["pa", "pc", "pd", "pe"])
    check("and the stranger in it is never put in front of the family to name",
          q(db, "select count(*) from clusters")[0][0], clusters)
    db.execute("delete from personal_people where name = 'Aunt Secretname'")
    db.commit()
    go()
    check("unticking someone hides their photographs again; one with another ticked person stays",
          (shown(), q(db, "select count(*) from photos where hidden_by = 'rule:personal'")[0][0]), (["pe"], 3))
    db.execute("insert into personal_people (name) values ('Aunt Secretname')")
    db.commit()
    go()
    check("and ticking them again shows them again", shown(), ["pa", "pc", "pd", "pe"])
    # as stored, not only as first looked at: a face that moved to someone the app
    # does not know keeps it out; a family's "not in it" for the ticked person too
    db.execute("insert into clusters (cluster_id, group_id, n) values ('c-x', 'c-x', 1)")
    # (the aunt stays; the owner's face is stored as someone unknown)
    db.execute("update faces set cluster_id = 'c-x', group_id = 'c-x' where hash = 'drive:pc' and cluster_id = 'c-o'")
    db.execute("update cluster_hashes set cluster_id = 'c-x', group_id = 'c-x' where hash = 'drive:pc' and cluster_id = 'c-o'")
    db.execute("insert into sync_state (key, value) values ('personal_strict', 'true') "
               "on conflict (key) do update set value = excluded.value")
    db.execute("insert into answers (id, who, scope, target, field, value, hashes) values "
               "(gen_random_uuid(), 'gran', 'file', 'drive:pe', 'not_in_photo', 'Aunt Secretname', array['drive:pe']), "
               "(gen_random_uuid(), 'gran', 'file', 'drive:pe', 'not_in_photo', 'Cousin Secretname', array['drive:pe'])")
    db.commit()
    go()
    check("a face stored as someone unknown, or a ticked name the family took off, keeps it out",
          ("pc" in shown(), "pe" in shown(), "pa" in shown()), (False, False, True))
    db.execute("update answers set status = 'undone' where field = 'not_in_photo'")
    db.execute("update faces set cluster_id = 'c-o', group_id = 'c-o' where hash = 'drive:pc' and cluster_id = 'c-x'")
    db.execute("update cluster_hashes set cluster_id = 'c-o', group_id = 'c-o' where hash = 'drive:pc' and cluster_id = 'c-x'")
    db.execute("update sync_state set value = 'false' where key = 'personal_strict'")
    db.commit()
    go()
    check("and puts it back when they agree again", ("pc" in shown(), "pe" in shown()), (True, True))
    drive.personal.remove("pa")
    go()
    check("a Personal file gone from Drive leaves the index", (shown(), q(db, "select count(*) from personal_seen "
          "where drive_id = 'pa'")[0][0]), (["pc", "pd", "pe"], 0))
    db.execute("delete from sync_state where key = 'personal_folder'")
    db.commit()
    go()
    check("the Communal listing never removes a Personal photograph, nor its holds",
          (shown(), q(db, "select count(*) from held where drive_id = 'pg'")[0][0]), (["pc", "pd", "pe"], 1))
    db.close()


def library(out):
    db = fresh_db(NAME + "_lib")
    tmp = tempfile.mkdtemp()
    bundle = os.path.join(tmp, "archives-library.sqlite")
    write_bundle(bundle)
    L = LibDrive.L
    drive = LibDrive()

    def go(g=None):
        g = g or LibGemini()
        w = CE.Worker(db, drive, g, LibFaces(), None, "root", "Media/Communal", workers=1, budget=100,
                      frames=20)
        with contextlib.redirect_stdout(out):
            r = w.run()
        return r, g

    # before the export is shared, the cloud judges what it finds
    drive.put("d7", "m-l7", L + "secret-l7.jpg")
    go()
    check("before the export, the cloud judged the file itself",
          q(db, "select count(*) from photos where hash = 'drive:d7'")[0][0], 1)

    # now the export arrives, with Drive as the library left it
    drive.bundle = bundle
    drive.put("d1", "m-l1", L + "secret-l1.jpg", w=3000, h=4000, rot=1)    # shown upright: 4000 x 3000
    drive.put("d2", "m-l2", L + "secret-l2.jpg")                            # landscape; its thumbnail is not
    drive.put("d3a", "m-l3", L + "secret-l3.jpg")
    drive.put("d3b", "m-l3", "Media/Communal/copies/secret-l3.jpg")         # a second copy
    drive.put("d5", "m-anything", L + "secret-l5.jpg")
    drive.put("d6", "m-l6-new", L + "secret-l6.jpg")                        # same name, new bytes
    drive.put("d8", "m-l8", L + "secret-l8.mp4", mime="video/mp4")
    drive.put("dh1", "m-h1", L + "secret-h1.jpg")
    drive.put("dnew", "m-new", L + "secret-new.jpg")                        # the library never saw it
    r, g = go()
    check("it paid only for what the library never described (and the changed file)",
          sorted(g.seen), ["d6", "dnew"])
    check("a file the library held out was never shown to the classifier", "dh1" in g.seen, False)
    held = dict(q(db, "select drive_id, reason from held"))
    check("held: nudity stays held, the second copy is a duplicate",
          (held.get("dh1"), held.get("d3b")), ("nudity", "duplicate"))
    bound = dict(q(db, "select hash, drive_id from photos where source = 'seed'"))
    check("bound by md5, the copy at the library's own path preferred",
          (bound["b1"], bound["b2"], bound["b3"], bound["b8"]), ("d1", "d2", "d3a", "d8"))
    check("bound by path only where the library knew no md5", bound["b5"], "d5")
    check("a changed file under the same name is NOT given the library's verdict",
          (bound["b6"], q(db, "select count(*) from photos where hash = 'drive:d6'")[0][0]), (None, 1))
    check("the library row replaced the cloud's row for the same file",
          (bound["b7"], q(db, "select count(*) from photos where hash = 'drive:d7'")[0][0]), ("d7", 0))
    vis = {h for (h,) in q(db, "select hash from photos where visible")}
    check("a library photo not on Drive is kept, and shown nowhere", ("b4" in bound, "b4" in vis), (True, False))
    grp = dict(q(db, "select cluster_id, group_id from clusters where pinned"))
    check("the library's groups are kept: merged stay merged, apart stay apart",
          (grp["c1"] == grp["c2"], grp["c3"] != grp["c4"]), (True, True))
    names = {g: (n, a, f) for g, n, a, f in q(db, "select group_id, name, answered, flagged from group_names")}
    check("the journal names a group", names[grp["c1"]][0], "Asha Secretname")
    check("a later 'needs identifying' re-opens a declined face, flagged",
          names[grp["c3"]][1:], (False, True))
    check("a later name closes a face that was flagged", names[grp["c4"]][:2], ("Meera Secretname", True))
    queue = [g for (g,) in q(db, "select group_id from queue order by rank")]
    check("the face the library asked about is asked first, before a bigger one",
          (queue[:1], grp["c6"] in queue), ([grp["c3"]], True))
    shown = {k for (k,) in q(db, "select hero_face from queue union all "
                                 "select unnest(sample_faces) from queue union all "
                                 "select cover_face from people where cover_face is not null")}
    check("a turned thumbnail's box is never drawn",
          (q(db, "select share from faces where key = 'b2::0'")[0][0], "b2::0" in shown), (None, False))
    check("a box-less face is never drawn", "b2::1" in shown, False)
    unjudged = {k for (k,) in q(db, "select f.key from faces f join photos p on p.hash = f.hash "
                                    "where p.media = 'video' and f.frame is null")}
    check("a video face is never drawn without a frame of its own", bool(shown & unjudged), False)
    fr = dict(q(db, "select key, status from frames"))
    check("a flagged face seen only in a video is asked, on its own judged frame",
          (fr.get("b8:b8_t3000:0"), q(db, "select hero_face from queue where group_id = %s", grp["c7"])),
          ("ok", [("b8:b8_t3000:0",)]))
    check("a frame that is not clean is held, never shown",
          (fr.get("b8:b8_t5000:0"), grp["c8"] in queue,
           q(db, "select jpeg is null from frames where key = 'b8:b8_t5000:0'")[0][0]), ("held", False, True))
    check("a frame without the person in it is not shown", (fr.get("b8:b8_t7000:0"), grp["c9"] in queue),
          ("noface", False))
    check("a rate-limited judgement is recorded as an error, never as a verdict",
          (fr.get("b8:b8_t8000:0"), grp["c10"] in queue), ("error", False))
    check("a named person seen only in a video gets a face in People",
          q(db, "select cover_face from people where name = 'Ravi Secretname'")[0][0], "b8:b8_t1000:0")
    check("a library box on a video (its own frame grab, not Drive's) is never drawn",
          (q(db, "select share from faces where key = 'b8::0'")[0][0], "b8::0" in shown), (None, False))
    check("an upright thumbnail of a turned photo keeps its box",
          q(db, "select share is not null from faces where key = 'b1::0'")[0][0], True)
    people = dict(q(db, "select name, photo_count from people"))
    check("people named only in the library's own record are listed too",
          sorted(people), ["Asha Secretname", "Dev Secretname", "Meera Secretname", "Ravi Secretname"])
    check("the journal is kept whole; its cluster answers count",
          (q(db, "select count(*) from journal")[0][0],
           q(db, "select count(*) from answers where reason = 'the library journal'")[0][0]), (11, 10))

    # the same export again changes nothing and costs nothing
    asked = len(drive.frames_asked)
    r, g = go()
    check("the same export is imported once", (g.seen, r.get("library_photos", 0)), ([], 0))
    check("the next run tries the next frame and the errored one, and judges nothing twice",
          (sorted(drive.frames_asked[asked:]), g.frames_judged), ([("d8", 6000), ("d8", 8000)], 2))
    check("the errored frame, judged again, is now shown",
          q(db, "select hero_face from queue where group_id = %s", grp["c10"]), [("b8:b8_t8000:0",)])
    check("so the face whose best frame was held is asked on its next one",
          q(db, "select hero_face from queue where group_id = %s", grp["c8"]), [("b8:b8_t6000:0",)])

    # two relatives name the same face differently, at once: both answers count,
    # neither replaces the other, and the face stays asked - first - until a
    # third breaks the tie (Krish, 2026-10-05)
    def vote(who, value):
        db.execute("insert into answers (id, who, scope, target, field, value) values "
                   "(gen_random_uuid(), %s, 'cluster', 'c6', 'person', %s)", (who, value))
        db.commit()
    vote("asha", "Kamala Secretname")
    vote("dev", "Ravi Secretname")
    vote("dev", "Sunil Secretname")            # Dev changes his mind: still one vote, his latest
    go()
    tie = q(db, "select name, answered, contested from group_names where group_id = %s", grp["c6"])
    queue = [g for (g,) in q(db, "select group_id from queue order by rank")]
    check("a tie is kept, shows the first name given, and is asked first",
          (tie, queue[:1]), ([("Kamala Secretname", False, True)], [grp["c6"]]))
    vote("meera", "sunil  secretname")         # the same name, typed differently
    go()
    settled = q(db, "select name, answered, contested from group_names where group_id = %s", grp["c6"])
    check("a third answer settles it, in the spelling most used, and the face leaves the queue",
          (settled, grp["c6"] in [g for (g,) in q(db, "select group_id from queue")]),
          ([("Sunil Secretname", True, False)], False))

    # later: the purged file turns up, the missing photo arrives, one leaves
    drive.put("dh2", "m-h2", "Media/Communal/2020/secret-again.jpg")
    drive.put("d4", "m-l4", L + "secret-l4.jpg")
    del drive.files["d1"]
    r, g = go()
    check("a purged photo that turns up is held, never classified",
          ("dh2" in g.seen, dict(q(db, "select drive_id, reason from held")).get("dh2")), (False, "removed"))
    check("the missing library photo binds when it arrives",
          q(db, "select drive_id from photos where hash = 'b4'")[0][0], "d4")
    check("a library photo whose file left keeps what the library knew",
          q(db, "select drive_id is null, description is not null, "
                "(select count(*) from faces where hash = 'b1') from photos where hash = 'b1'"),
          [(True, True, 2)])
    drive.put("d1b", "m-l1", L + "secret-l1.jpg")
    go()
    check("and re-binds when it comes back",
          q(db, "select drive_id from photos where hash = 'b1'")[0][0], "d1b")

    # an export that is not what it says it is stops the run
    bad = os.path.join(tmp, "broken.sqlite")
    write_bundle(bad, broken=True)
    db2 = fresh_db(NAME + "_lib2")
    w = CE.Worker(db2, LibDrive(bad), LibGemini(), None, None, "root", "Media/Communal", workers=1)
    try:
        with contextlib.redirect_stdout(out):
            w.run()
        check("an export whose counts disagree stops the run", "ran", "stopped")
    except RuntimeError:
        check("an export whose counts disagree stops the run", "stopped", "stopped")
    check("and imports nothing", q(db2, "select count(*) from photos")[0][0], 0)
    db2.close()
    db.close()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
