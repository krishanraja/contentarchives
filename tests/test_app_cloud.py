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
  8. NOTHING but numbers reaches stdout: no path, no name, no description

A database test that cannot reach its database FAILS - a green run with
Postgres down once reported six tests as passing that had not run.
"""

import contextlib
import io
import json
import os
import sys

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
    print("8. the public log carries numbers only")
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


if __name__ == "__main__":
    sys.exit(main())
