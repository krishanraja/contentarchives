r"""Build and keep the family app's index from Google Drive alone. No PC, no D:.

    python stages/13_app/cloud_enrich.py --budget 300      # what the workflow runs
    python stages/13_app/cloud_enrich.py --budget 0        # reconcile + rebuild only

Krish, 2026-10-04: "this needs to read from H:\My Drive\ContentLibrary\Media\
Communal, always on and accessible, no reliance on a local drive" - and, when
the first design still seeded the index from the library machine: "Nothing
about the D drive exists for this session, there is not even a D drive
connected". So everything the app knows is made here, from Drive, by the ONE
writer of the index. It runs as a GitHub Actions workflow
(.github/workflows/archives-enrich.yml), daily and on demand.

EACH RUN

  1. list the Communal folder through the read-only service account, with the
     camera's own date and GPS from Drive's metadata
  2. reconcile: a file gone from Drive leaves the index (learning 57), but a
     listing that looks broken removes nothing
  3. new files, until --budget or the spend cap: Drive's 1024px rendering,
     judged by the library's OWN three passes (classify_live.call with the
     base, rich and sensitivity prompts, verbatim), then the SAME publication
     rule as the seed (share_set.nudity_hold): no adult or unclear-age nudity,
     nothing sexual or intimate, nothing never judged, photographs and videos
     only. Anything held goes to `held` and is never shown.
  4. faces: insightface buffalo_l on a 512px image, exactly as faces_embed.py
     runs on the library's thumbnails; each face joins the nearest cluster at
     0.55 (cluster_faces.py's measured threshold) or starts one at det >= 0.60.
     Cluster ids are frozen and never reused.
  5. groups: clusters whose centroids meet at 0.68 are one person
     (chain_rounds.ps1's merge), never joining two different names
     (merge_clusters.py's rule). Then the naming queue, suggestions and people
     are rebuilt from scratch - they are derived, and a rebuild is the cheapest
     way to keep them true.
  6. a receipt in `snapshots`: counts and dollars spent.

THE LOG IS PUBLIC

This runs in a public repository, so stdout carries COUNTS ONLY: never a path,
a file name, a description or a person's name. say() refuses anything but
numbers, and tests/test_app_cloud.py fails if a fixture's names reach stdout.

SPEND

Gemini reports tokens; each pass is priced at classify_live's own rates and
the run stops starting new files at --cap-usd. Files already in flight finish,
so the cap can be passed by at most 2 x --workers files' worth (the pool keeps
two per worker queued) - about 3 cents at the default 8 workers.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import io
import json
import os
import re
import sys
import tempfile
import time

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
from share_set import nudity_hold                                # noqa: E402

JOIN, START, MERGE = 0.55, 0.60, 0.68      # cluster_faces / merge (chain_rounds)
SUBJECT_SHARE = 0.12                       # people_sheet.SUBJECT_SHARE
SUGGEST_MIN = 0.40
FACE_PX, VIEW_PX = 512, 1024
MAX_QUEUE = 5000
YEAR_DIR = re.compile(r"(?:^|/)((?:18|19|20)\d\d)(?:/|$)")


# ---------------------------------------------------------------- logging ---

def say(event: str, **nums) -> None:
    """One line of numbers. Anything else is a bug: this log is public."""
    for k, v in nums.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise TypeError("say() takes numbers only, got {} for {}".format(type(v).__name__, k))
    if not re.fullmatch(r"[a-z][a-z0-9 _-]*", event):
        raise ValueError("say() events are fixed lowercase words")
    print("{:<18} {}".format(event, "  ".join(
        "{}={}".format(k, round(v, 4) if isinstance(v, float) else v)
        for k, v in nums.items())), flush=True)


# ------------------------------------------------------------- the rule ----

def cloud_hold(media: str, v: dict) -> str:
    """The seed's rule for a file the cloud judged itself (web/lib/share.ts
    is the same rule; both read stages/13_app/nudity_cases.json)."""
    if media == "photo" and (v.get("kind") or "") != "photo":
        return "not a photograph"
    sens = {k: str(v.get(k) or "").lower() for k in ("nudity", "subject_age", "sexual")}
    return nudity_hold(str(v.get("sensitivity") or "").lower(), sens, False)


# ------------------------------------------------------------ the world ----

class Drive:
    """Google Drive as the read-only service account. Sees Communal only."""
    FIELDS = ("nextPageToken, files(id, name, mimeType, md5Checksum, "
              "imageMediaMetadata(time, location, width, height), "
              "videoMediaMetadata(width, height))")

    def __init__(self, sa_json: str):
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        creds = service_account.Credentials.from_service_account_info(
            json.loads(sa_json), scopes=["https://www.googleapis.com/auth/drive.readonly"])
        self.s = AuthorizedSession(creds)

    def list_tree(self, root: str, prefix: str) -> list:
        out, stack = [], [(root, prefix)]
        while stack:
            fid, rel = stack.pop()
            token = ""
            while True:
                r = self.s.get("https://www.googleapis.com/drive/v3/files", params={
                    "q": "'{}' in parents and trashed = false".format(fid),
                    "fields": self.FIELDS, "pageSize": 1000,
                    "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                    **({"pageToken": token} if token else {})}, timeout=60)
                r.raise_for_status()
                j = r.json()
                for f in j.get("files", []):
                    p = "{}/{}".format(rel, f["name"]) if rel else f["name"]
                    if f["mimeType"] == "application/vnd.google-apps.folder":
                        stack.append((f["id"], p))
                    elif re.match(r"^(image|video)/", f["mimeType"]):
                        im = f.get("imageMediaMetadata") or {}
                        vm = f.get("videoMediaMetadata") or {}
                        loc = im.get("location") or {}
                        out.append({"id": f["id"], "rel": p, "mime": f["mimeType"],
                                    "md5": f.get("md5Checksum"), "time": im.get("time"),
                                    "lat": loc.get("latitude"), "lon": loc.get("longitude"),
                                    "w": im.get("width") or vm.get("width"),
                                    "h": im.get("height") or vm.get("height")})
                token = j.get("nextPageToken") or ""
                if not token:
                    break
        return out

    def image(self, fid: str, px: int):
        r = self.s.get("https://www.googleapis.com/drive/v3/files/" + fid,
                       params={"fields": "thumbnailLink", "supportsAllDrives": "true"}, timeout=60)
        if r.status_code != 200:
            return None
        link = (r.json() or {}).get("thumbnailLink")
        if not link:
            return None
        t = self.s.get(re.sub(r"=s\d+(-[a-z]+)?$", "=s{}".format(px), link), timeout=60)
        return t.content if t.status_code == 200 and t.content else None


class Gemini:
    """The library's own classifier and embedder, priced at their own rates."""

    def __init__(self, key: str):
        import classify_live as CL
        import embed_descriptions as ED
        self.CL, self.ED, self.key = CL, ED, key

    def classify(self, jpeg: bytes):
        CL = self.CL
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            fh.write(jpeg)
            path = fh.name
        try:
            out, usd = {}, 0.0
            # the same output budgets classify_live.main() gives each pass
            for prompt, max_out in ((CL.PROMPT, 800), (CL.RICH_PROMPT, 1400), (CL.SENS_PROMPT, 200)):
                txt, tin, tout = CL.call([path], self.key, prompt=prompt, max_out=max_out)
                usd += (tin * CL.IN_PER_M + tout * CL.OUT_PER_M) / 1e6
                out.update(CL.parse(txt))
            return out, usd
        finally:
            os.unlink(path)

    def embed(self, text: str):
        v = self.ED.embed([text], self.key)[0]
        return v, len(text) / 4 * self.ED.PER_M / 1e6


class Faces:
    """insightface buffalo_l at 512px - faces_embed.py's model and size."""

    def __init__(self):
        from insightface.app import FaceAnalysis
        self.app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=-1, det_size=(FACE_PX, FACE_PX))

    def detect(self, jpeg: bytes) -> list:
        import numpy as np
        from PIL import Image
        with Image.open(io.BytesIO(jpeg)) as im:
            im = im.convert("RGB")
            im.thumbnail((FACE_PX, FACE_PX))
            W, H = im.size
            arr = np.array(im)[:, :, ::-1]
        out = []
        for fc in self.app.get(arr):
            v = np.asarray(fc.embedding, dtype=np.float32)
            v = v / (float(np.linalg.norm(v)) or 1.0)
            x1, y1, x2, y2 = [float(t) for t in fc.bbox]
            share = min(x2 - x1, y2 - y1) / float(min(W, H) or 1)
            out.append({"bbox": [max(0.0, x1 / W), max(0.0, y1 / H), min(1.0, x2 / W), min(1.0, y2 / H)],
                        "det": float(fc.det_score), "emb": v, "share": share})
        return out


def load_geocoder():
    """The offline GeoNames index, if its data is present (the workflow fetches it)."""
    try:
        import geocode
        if os.path.isdir(geocode.DEFAULT_DATA):
            return geocode.Geocoder(geocode.DEFAULT_DATA)
    except Exception:                                            # noqa: BLE001
        pass
    return None


# ----------------------------------------------------------------- helpers --

def vec(v) -> str:
    return "[" + ",".join("{:.6f}".format(float(x)) for x in v) + "]"


def parse_vec(s):
    import numpy as np
    if s is None:
        return None
    if isinstance(s, str):
        return np.array([float(x) for x in s.strip("[]").split(",")], dtype=np.float32)
    return np.asarray(s, dtype=np.float32)


def when(f: dict):
    """(taken_at, year): the camera's clock if Drive read one, else the year folder."""
    t = f.get("time")
    if t:
        try:
            d = dt.datetime.strptime(t[:19], "%Y:%m:%d %H:%M:%S")
            if 1850 <= d.year <= dt.date.today().year + 1:
                return d.replace(tzinfo=dt.timezone.utc), d.year
        except ValueError:
            pass
    m = YEAR_DIR.search(f.get("rel") or "")
    return None, (int(m.group(1)) if m else None)


# ------------------------------------------------------------------ worker --

class Worker:
    def __init__(self, db, drive, gemini, faces, geo, folder, prefix,
                 budget=300, cap_usd=60.0, workers=8, max_minutes=None):
        self.db, self.drive, self.gemini, self.faces, self.geo = db, drive, gemini, faces, geo
        self.folder, self.prefix = folder, prefix
        self.budget, self.cap, self.workers = budget, cap_usd, workers
        # A DEADLINE, NOT A KILL: GitHub ends a job at 6 h, and a killed run
        # never reaches group(), rebuild() or its receipt - the parts the app
        # reads. Past the deadline nothing new starts, exactly like the cap.
        self.deadline = None if max_minutes is None else time.time() + 60 * max_minutes
        self.c = collections.Counter()
        self.spent = 0.0
        self.errors = collections.Counter()

    # -- clusters, in memory for the run --------------------------------
    def load_clusters(self):
        """Centroids in preallocated arrays, as cluster_faces.cluster() keeps
        them: unit centroids C for matching, running sums S for updating.
        Re-normalising every centroid per face would cost hours at 20k."""
        import numpy as np
        rows = self.db.execute("select cluster_id, centroid::text, n from clusters "
                               "where centroid is not null").fetchall()
        cap = max(4096, 2 * len(rows))
        self.C = np.zeros((cap, 512), np.float32)
        self.S = np.zeros((cap, 512), np.float32)
        self.cid, self.cn = [], []
        for cid, cen, n in rows:
            v = parse_vec(cen)
            k = len(self.cid)
            self.cid.append(cid)
            self.cn.append(max(int(n or 1), 1))
            self.C[k] = v / (float(np.linalg.norm(v)) or 1.0)
            self.S[k] = self.C[k] * self.cn[k]
        # A NEW ID MUST CLEAR EVERY ID ALREADY HANDED OUT (learning 72): the
        # counter OR the highest k-id in the table, whichever is higher, so a
        # run that died before saving its counter can never reissue an id that
        # already names somebody's face.
        r = self.db.execute("select value from sync_state where key = 'next_cluster'").fetchone()
        top = self.db.execute(
            "select max(substring(cluster_id from 2)::int) from clusters where cluster_id ~ '^k[0-9]+$'").fetchone()
        self.next_id = max(int(r[0]) if r else 1, (int(top[0]) + 1) if top and top[0] is not None else 1)
        self.dirty = set()

    def assign(self, emb, det):
        """-> cluster id, or None for a weak face that matches nobody."""
        import numpy as np
        k = len(self.cid)
        if k:
            sims = self.C[:k] @ emb
            j = int(np.argmax(sims))
            if sims[j] >= JOIN:
                self.S[j] += emb
                self.cn[j] += 1
                self.C[j] = self.S[j] / (float(np.linalg.norm(self.S[j])) or 1.0)
                self.dirty.add(j)
                return self.cid[j]
        if det < START:
            return None
        if k == len(self.C):                         # grow, as cluster_faces does
            self.C = np.resize(self.C, (2 * k, 512))
            self.S = np.resize(self.S, (2 * k, 512))
            self.C[k:] = 0
            self.S[k:] = 0
        cid = "k{}".format(self.next_id)            # k: made in the cloud, never confused with the library's c-ids
        self.next_id += 1
        self.cid.append(cid)
        self.cn.append(1)
        self.C[k] = emb
        self.S[k] = emb
        self.dirty.add(k)
        return cid

    def save_clusters(self):
        for j in sorted(self.dirty):
            self.db.execute(
                "insert into clusters (cluster_id, group_id, centroid, n) values (%s, %s, %s::extensions.vector, %s) "
                "on conflict (cluster_id) do update set centroid = excluded.centroid, n = excluded.n",
                (self.cid[j], self.cid[j], vec(self.C[j]), self.cn[j]))
        self.db.execute(
            "insert into sync_state (key, value) values ('next_cluster', %s) "
            "on conflict (key) do update set value = excluded.value", (str(self.next_id),))
        self.db.commit()
        self.dirty = set()

    # -- the run --------------------------------------------------------
    def run(self) -> dict:
        t0 = time.time()
        files = self.drive.list_tree(self.folder, self.prefix)
        self.c["listed"] = len(files)
        say("listed", files=len(files))
        self.reconcile(files)
        self.load_clusters()
        self.process(files)
        self.save_clusters()
        self.group()
        self.rebuild()
        receipt = dict(self.c, spent_usd=round(self.spent, 4), seconds=int(time.time() - t0),
                       errors=sum(self.errors.values()))
        self.db.execute("insert into snapshots (kind, counts) values ('drive-sync', %s::jsonb)",
                        (json.dumps(receipt),))
        self.db.commit()
        say("done", **{k: v for k, v in receipt.items() if isinstance(v, (int, float))})
        for name, n in self.errors.most_common():
            say("error", **{re.sub(r"[^a-z0-9_]", "_", name.lower())[:40] or "unknown": n})
        return receipt

    def reconcile(self, files):
        ids = {f["id"] for f in files}
        known = [r[0] for r in self.db.execute(
            "select drive_id from photos where drive_id is not null").fetchall()]
        gone = [k for k in known if k not in ids]
        if not files or (len(known) > 20 and len(gone) > len(known) * 0.2):
            self.c["refused_removal"] = len(gone)
            say("refused removal", gone=len(gone), known=len(known))
        elif gone:
            self.db.execute("delete from photos where drive_id = any(%s)", (gone,))
            self.c["removed"] = len(gone)
        self.db.execute("delete from held where not (drive_id = any(%s))", (list(ids),))
        self.db.commit()

    def process(self, files):
        have = {r[0] for r in self.db.execute(
            "select drive_id from photos where drive_id is not null union select drive_id from held").fetchall()}
        fresh = sorted((f for f in files if f["id"] not in have), key=lambda f: f["rel"])
        self.c["waiting_before"] = len(fresh)
        todo = fresh[:max(0, self.budget)]
        if not todo:
            return
        done = 0
        with cf.ThreadPoolExecutor(max_workers=self.workers) as pool:
            futs = {}
            it = iter(todo)
            for f in it:                      # keep the pool fed, never the whole list at once
                futs[pool.submit(self.judge, f)] = f
                if len(futs) >= self.workers * 2:
                    break
            while futs:
                fut = next(cf.as_completed(futs))
                f = futs.pop(fut)
                try:
                    self.store(f, *fut.result())
                except Exception as e:                           # noqa: BLE001
                    self.db.rollback()
                    self.errors[type(e).__name__] += 1
                done += 1
                if done % 50 == 0:
                    self.save_clusters()           # a killed run loses at most 50 files' centroids
                if done % 100 == 0:
                    say("progress", done=done, of=len(todo), spent_usd=self.spent,
                        added=self.c["added"], held=self.c["held"])
                if self.spent >= self.cap:
                    if not self.c["cap_reached"]:
                        say("spend cap", spent_usd=self.spent, cap_usd=self.cap)
                    self.c["cap_reached"] = 1
                    continue                   # let in-flight files finish; start no more
                if self.deadline is not None and time.time() >= self.deadline:
                    if not self.c["time_up"]:
                        say("time up", done=done, of=len(todo))
                    self.c["time_up"] = 1
                    continue
                nxt = next(it, None)
                if nxt is not None:
                    futs[pool.submit(self.judge, nxt)] = nxt

    def judge(self, f):
        """Network work only (thread pool): image, verdict, embedding."""
        jpeg = self.drive.image(f["id"], VIEW_PX)
        if not jpeg:
            return None, None, None, 0.0
        try:
            v, usd = self.gemini.classify(jpeg)
        except RuntimeError as e:
            if str(e).startswith("BLOCKED"):
                return jpeg, {"_blocked": True}, None, 0.0
            raise
        emb, eusd = None, 0.0
        media = "video" if f["mime"].startswith("video/") else "photo"
        if not cloud_hold(media, v) and (v.get("description") or "").strip():
            emb, eusd = self.gemini.embed(v["description"].strip()[:2000])
        return jpeg, v, emb, usd + eusd

    def store(self, f, jpeg, v, emb, usd):
        self.spent += usd
        if jpeg is None:
            self.c["no_image"] += 1                  # retried next run
            return
        media = "video" if f["mime"].startswith("video/") else "photo"
        why = "the classifier would not judge it" if v.get("_blocked") else cloud_hold(media, v)
        if why:
            self.db.execute(
                "insert into held (drive_id, rel_path, reason) values (%s, %s, %s) "
                "on conflict (drive_id) do update set reason = excluded.reason, at = now()",
                (f["id"], f["rel"], why))
            self.db.commit()
            self.c["held"] += 1
            return
        taken, year = when(f)
        place, region, country = (str(v.get("place") or "").strip()[:80] or None), None, None
        if self.geo and f.get("lat") is not None and f.get("lon") is not None:
            g = self.geo.lookup(float(f["lat"]), float(f["lon"]))
            if g and g.get("km", 999) <= 25:
                place, region, country = g["name"], g.get("region") or None, g.get("country") or None
        h = "drive:" + f["id"]
        self.db.execute(
            "insert into photos (hash, drive_id, rel_path, md5, media, taken_at, year, place, region, "
            "country, description, objects, activity, occasion, mood, day_key, width, height, lat, lon, "
            "embedding, source) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            "%s::extensions.vector,'cloud') on conflict (hash) do nothing",
            (h, f["id"], f["rel"], f.get("md5"), media, taken, year, place, region, country,
             (v.get("description") or None), (v.get("objects") or None), (v.get("activity") or None),
             (v.get("occasion") or None), (v.get("mood") or None),
             taken.date().isoformat() if taken else None, f.get("w"), f.get("h"),
             f.get("lat"), f.get("lon"), vec(emb) if emb is not None else None))
        faces = self.faces.detect(jpeg) if self.faces else []
        n_here = len(faces)
        for i, fc in enumerate(faces):
            cid = self.assign(fc["emb"], fc["det"])
            if cid is None:
                continue
            key = "{}::{}".format(h, i)
            self.db.execute(
                "insert into faces (key, hash, group_id, cluster_id, bbox, only_face, score, share, embedding) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector) on conflict (key) do nothing",
                (key, h, cid, cid, [round(x, 5) for x in fc["bbox"]], n_here == 1, fc["det"],
                 round(fc["share"], 4), vec(fc["emb"])))
            self.db.execute(
                "insert into clusters (cluster_id, group_id, n) values (%s, %s, 0) on conflict do nothing",
                (cid, cid))
            self.db.execute(
                "insert into cluster_hashes (cluster_id, group_id, hash) values (%s,%s,%s) on conflict do nothing",
                (cid, cid, h))
            self.c["faces"] += 1
        self.db.commit()
        self.c["added"] += 1

    # -- people ------------------------------------------------------------
    def group(self):
        """Clusters -> people, by running group centroids (merge_clusters.py),
        never joining two different names."""
        import numpy as np
        rows = self.db.execute(
            "select c.cluster_id, c.centroid::text, c.n, cn.name from clusters c "
            "left join cluster_names cn on cn.cluster_id = c.cluster_id "
            "where c.centroid is not null order by c.n desc, c.cluster_id").fetchall()
        gid, gsum, gnames, of = [], [], [], {}
        for cid, cen, n, name in rows:
            v = parse_vec(cen) * max(int(n or 1), 1)
            if gsum:
                G = np.array(gsum, dtype=np.float32)
                G = G / np.maximum(np.linalg.norm(G, axis=1, keepdims=True), 1e-9)
                u = v / (float(np.linalg.norm(v)) or 1.0)
                sims = G @ u
                order = np.argsort(-sims)
                placed = False
                for j in order[:5]:
                    if sims[j] < MERGE:
                        break
                    if name and gnames[j] and name not in gnames[j]:
                        continue                  # two people with two names stay two
                    gsum[j] = gsum[j] + v
                    if name:
                        gnames[j].add(name)
                    of[cid] = gid[j]
                    placed = True
                    break
                if placed:
                    continue
            gid.append(cid)
            gsum.append(v)
            gnames.append({name} if name else set())
            of[cid] = cid
        moved = 0
        for cid, g in of.items():
            r = self.db.execute("update clusters set group_id = %s where cluster_id = %s and group_id <> %s",
                                (g, cid, g))
            moved += r.rowcount or 0
        self.db.execute("update cluster_hashes ch set group_id = c.group_id from clusters c "
                        "where c.cluster_id = ch.cluster_id and ch.group_id <> c.group_id")
        self.db.execute("update faces f set group_id = c.group_id from clusters c "
                        "where c.cluster_id = f.cluster_id and f.group_id is distinct from c.group_id")
        self.db.commit()
        self.c["clusters"] = len(rows)
        self.c["groups"] = len(gid)
        self.c["regrouped"] = moved

    def rebuild(self):
        """Queue, suggestions and people: derived, so rebuilt whole."""
        import numpy as np
        db = self.db
        names = dict(db.execute("select group_id, name from group_names where name is not null").fetchall())
        answered = {r[0] for r in db.execute("select group_id from group_names where answered").fetchall()}
        faces = collections.defaultdict(list)
        for key, h, g, score, share, only in db.execute(
                "select f.key, f.hash, f.group_id, f.score, coalesce(f.share, 0), f.only_face "
                "from faces f join photos p on p.hash = f.hash and not p.hidden "
                "where f.group_id is not null").fetchall():
            faces[g].append((key, h, float(score or 0), float(share), bool(only)))
        photos = {g: len({h for _, h, _, _, _ in fs}) for g, fs in faces.items()}

        def cover(fs):
            good = [f for f in fs if f[3] >= SUBJECT_SHARE]
            if not good:
                return None
            return max(good, key=lambda f: (f[4], f[2] * f[3]))

        # one centroid per NAME (a person may span several groups)
        cents = collections.defaultdict(lambda: None)
        for g, cen, n in db.execute(
                "select group_id, centroid::text, n from clusters where centroid is not null").fetchall():
            v = parse_vec(cen) * max(int(n or 1), 1)
            cents[g] = v if cents[g] is None else cents[g] + v
        by_name, cover_of = {}, {}
        for g, name in names.items():
            if cents[g] is not None:
                by_name[name] = cents[g] if name not in by_name else by_name[name] + cents[g]
            c = cover(faces.get(g, []))
            if c and (name not in cover_of or (c[4], c[2] * c[3]) > (cover_of[name][4], cover_of[name][2] * cover_of[name][3])):
                cover_of[name] = c
        labels = [n for n in by_name if n in cover_of]
        M = None
        if labels:
            M = np.stack([by_name[n] / (float(np.linalg.norm(by_name[n])) or 1.0) for n in labels])

        queue = []
        for g, fs in sorted(faces.items(), key=lambda kv: -photos[kv[0]]):
            if g in names or g in answered or photos[g] < 2:
                continue
            subj = sorted((f for f in fs if f[3] >= SUBJECT_SHARE), key=lambda f: (-f[4], -f[2]))
            if not subj:
                continue
            hero, seen, samples = subj[0], {subj[0][1]}, []
            for f in sorted(subj[1:], key=lambda f: -f[2]):
                if f[1] not in seen and len(samples) < 4:
                    samples.append(f[0])
                    seen.add(f[1])
            sugg = []
            if M is not None and cents[g] is not None:
                u = cents[g] / (float(np.linalg.norm(cents[g])) or 1.0)
                sims = M @ u
                for i in np.argsort(-sims)[:4]:
                    if sims[i] >= SUGGEST_MIN:
                        sugg.append({"name": labels[i], "face": cover_of[labels[i]][0],
                                     "score": round(float(sims[i]), 3)})
            queue.append((g, len(queue), photos[g], hero[0], samples, json.dumps(sugg)))
            if len(queue) >= MAX_QUEUE:
                break

        people = []
        for name in sorted(set(names.values())):
            gs = [g for g, n in names.items() if n == name]
            people.append((name, cover_of[name][0] if name in cover_of else None,
                           len({h for g in gs for _, h, _, _, _ in faces.get(g, [])})))

        db.execute("delete from queue")
        db.execute("delete from people")
        with db.cursor() as cur:
            cur.executemany("insert into queue (group_id, rank, photo_count, hero_face, sample_faces, suggestions) "
                            "values (%s, %s, %s, %s, %s, %s::jsonb)", queue)
            cur.executemany("insert into people (name, cover_face, photo_count) values (%s, %s, %s)", people)
        db.commit()
        self.c["queue"] = len(queue)
        self.c["people"] = len(people)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=int, default=int(os.environ.get("BUDGET", "300")))
    ap.add_argument("--cap-usd", type=float, default=float(os.environ.get("SPEND_CAP_USD", "60")))
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "8")))
    ap.add_argument("--max-minutes", type=float,
                    default=float(os.environ["MAX_MINUTES"]) if os.environ.get("MAX_MINUTES") else None)
    ap.add_argument("--no-faces", action="store_true")
    a = ap.parse_args()
    need = ["DATABASE_URL", "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_API_KEY_ARCHIVES",
            "DRIVE_COMMUNAL_FOLDER_ID"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        print("STOPPING: missing environment: " + ", ".join(missing))
        return 1
    import psycopg
    db = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None)
    w = Worker(db, Drive(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
               Gemini(os.environ["GOOGLE_API_KEY_ARCHIVES"]),
               None if a.no_faces else Faces(), load_geocoder(),
               os.environ["DRIVE_COMMUNAL_FOLDER_ID"],
               os.environ.get("DRIVE_REL_PREFIX", "Media/Communal"),
               budget=a.budget, cap_usd=a.cap_usd, workers=a.workers, max_minutes=a.max_minutes)
    w.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
