r"""Seed the family app's cloud index from the library. Re-runnable; dry by default.

    python stages/13_app/seed_index.py                 # build and report, upload nothing
    python stages/13_app/seed_index.py --check-frames  # sensitivity-check video face frames (Gemini, ~$)
    python stages/13_app/seed_index.py --apply         # upload, reconcile, write the receipt

WHY A SEED AND NOT A SYNC

Krish, 2026-10-04: the app must read the Communal side from Google Drive,
"always on and accessible, no reliance on a local drive". The PHOTOGRAPHS come
from Drive. What Drive does not have is everything this library learned about
them - 85,000 descriptions, the face groups, who is who, where and when - and
that lives here. So it is copied up once, and again whenever the library learns
more (the nightly chain), while the app keeps working with this machine off.
Files that reach Drive later are described by the app itself.

WHAT GOES UP, AND WHAT NEVER DOES

Only the share set (share_set.py): Communal photographs and videos that pass
every rule, including Krish's nudity rule. Every image byte uploaded comes
from a share-set hash - and the only image bytes uploaded at all are video
face frames, because Drive keeps one thumbnail per video and the face may be
anywhere in it. A video frame goes up only after a sensitivity verdict on THAT
frame clears it (`--check-frames`): the classifier judged 2-5 frames of each
video, the face pass looked at up to 60, and an unjudged frame is not a safe
one.

  photos         share-set rows: description, place, people, embedding (joined
                 by HASH from desc-vectors, never by position - learning 45)
  clusters /     every face cluster on a shared photograph, its merge group and
  cluster_hashes the journal's current name for that group
  queue          build_game.select_queue(side Communal, allowed = share set),
                 the same selection Bharti's game uses, with the whole photo
                 ringed as the question and up to four more of the same person
  people         the family set only - names on shared photographs - each with
                 a cover face from a shared photograph
  suggestions    nearest named groups by face-embedding centroid, joined on
                 (hash, face_index) / (image, face_index) - never position

RECONCILE, NOT APPEND (learning 57)

Seed rows that left the share set are deleted from the cloud on every --apply,
and the receipt records counts and the answer watermark: app answers newer than
it overlay the seeded names until the next seed includes them.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import io
import json
import os
import sqlite3
import sys

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
import build_game as BG                                          # noqa: E402
import people_sheet as PS                                        # noqa: E402
from sides import side_of                                        # noqa: E402
from blocklist import blocked_hashes                             # noqa: E402
from share_set import share_set, nudity_hold, open_ro            # noqa: E402

AUDIT = P.AUDIT
STORE = r"D:\_enrichment"
DEFAULTS = {
    "db": os.path.join(AUDIT, "library.db"),
    "assign": os.path.join(AUDIT, "FACE-CLUSTERS.csv"),
    "video_assign": os.path.join(AUDIT, "FACE-CLUSTERS-VIDEO.csv"),
    "merges": os.path.join(AUDIT, "CLUSTER-MERGES.csv"),
    "answers": os.path.join(STORE, "answers.csv"),
    "tags": os.path.join(STORE, "content_tags.csv"),
    "faces": os.path.join(STORE, "faces.0.csv"),
    "video_faces": os.path.join(STORE, "faces.video.csv"),
    "vectors": os.path.join(AUDIT, "desc-vectors"),
    "events": os.path.join(AUDIT, "EVENTS.json"),
    "mirror": os.path.join(AUDIT, "h-mirror.csv"),
    "thumbs": r"D:\_thumbs",
    "frames": r"D:\_frames",
    "frame_verdicts": os.path.join(AUDIT, "APP-FRAME-SENSITIVITY.csv"),
    "out": os.path.join(AUDIT, "app-seed"),
}
SUGGEST_MIN, MAX_QUEUE, SAMPLES = 0.40, 3000, 4
RICH = ("description", "objects", "activity", "occasion", "mood",
        "place", "region", "country", "approx_year")


def read_csv(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def rel_path(path: str) -> str:
    """'D:\\ContentLibrary\\Media\\Communal\\2014\\a.jpg' -> 'Media/Communal/2014/a.jpg',
    the path the same file has under ContentLibrary on Drive."""
    p = path.replace("\\", "/")
    i = p.lower().find("/media/")
    return p[i + 1:] if i >= 0 else p.split("/")[-1]


# What stage 11 WRITES when a file reached H: - mirror_to_h.py,
# apply_mirror_deletions.py, verify_drive_by_mount.py, verify_drive_md5.py and
# patch_mirror_flatten.py all read exactly this pair. A sixth vocabulary lived
# here: ("ok", "copied", "verified", "skipped-identical"), none of which the
# writer has ever emitted, so this function returned 117 md5s out of 94,523
# rows and every seeded photo got md5 = NULL - the cloud's primary binding key,
# absent, with every count still agreeing. One definition of the word, taken
# from the writer, and the rows it refuses are counted out loud.
MIRROR_OK = ("written", "already-present")


def mirror_md5(path: str, log=None) -> dict:
    """blake2b -> md5 from the mirror journal: how a seeded row finds its Drive file."""
    out, refused = {}, 0
    for r in read_csv(path):
        if not (r.get("blake2b") and r.get("md5")):
            refused += 1
        elif (r.get("outcome") or "").strip().lower() in MIRROR_OK:
            out[r["blake2b"].lower()] = r["md5"].lower()
        else:
            refused += 1                     # copy failed, DEFERRED, no hash
    if log:
        log("mirror journal: {:,} md5s, {:,} rows refused".format(len(out), refused))
    return out


def load_vectors(folder: str, wanted: set) -> dict:
    import glob
    import numpy as np
    out = {}
    for s in sorted(glob.glob(os.path.join(folder, "shard-*.npz"))):
        with np.load(s, allow_pickle=False) as z:
            for h, v in zip(z["hash"].tolist(), z["vec"]):
                if h in wanted:
                    v = v.astype("float32")
                    n = float(np.linalg.norm(v)) or 1.0
                    out[h] = [round(float(x) / n, 6) for x in v]
    return out


def day_keys(events: str, wanted: set) -> dict:
    """hash -> the start of its event. Explicit hashes per event, never position."""
    if not os.path.exists(events):
        return {}
    data = json.load(io.open(events, encoding="utf-8"))
    out = {}
    for e in data.get("events", []):
        for h in e.get("hashes", []):
            if h in wanted:
                out[h] = e.get("start", "")
    return out


def journal_names(answers: str, group_of: dict) -> dict:
    """group -> the latest name a person gave it (any cluster in the group)."""
    out = {}
    for r in read_csv(answers):
        if r.get("field") == "person" and r.get("scope") == "cluster":
            v = (r.get("value") or "").strip()
            g = group_of.get(r["target"], r["target"])
            if v:
                out[g] = v
            else:
                out.pop(g, None)
    return out


def photo_rows(db, shared: dict, md5s: dict, vectors: dict, days: dict) -> list:
    res = collections.defaultdict(dict)
    hs = list(shared)
    for i in range(0, len(hs), 900):
        chunk = hs[i:i + 900]
        q = ",".join("?" * len(chunk))
        for h, f, v in db.execute(
                "SELECT hash, field, value FROM resolved WHERE hash IN ({}) "
                "AND field IN ({})".format(q, ",".join("?" * len(RICH))),
                chunk + list(RICH)):
            res[h][f] = v
        for h, d, y, w, ht in db.execute(
                "SELECT hash, MIN(date_taken), MIN(year), MAX(width), MAX(height) "
                "FROM files WHERE hash IN ({}) GROUP BY hash".format(q), chunk):
            res[h]["_date"], res[h]["_year"] = d, y
            res[h]["_w"], res[h]["_h"] = w, ht
    people = collections.defaultdict(set)
    for i in range(0, len(hs), 900):
        chunk = hs[i:i + 900]
        for h, p in db.execute("SELECT hash, person FROM photo_people WHERE hash IN ({})"
                               .format(",".join("?" * len(chunk))), chunk):
            if p:
                people[h].add(p)
    rows = []
    for h, s in shared.items():
        r = res.get(h, {})
        taken = None
        try:
            taken = dt.datetime.strptime(r.get("_date") or "", "%Y-%m-%d %H:%M:%S").isoformat() + "Z"
        except ValueError:
            pass
        y = r.get("_year")
        rows.append({
            "hash": h, "rel_path": rel_path(s["paths"][0]), "md5": md5s.get(h.lower()),
            "media": "video" if s["media"] == "video" else "photo",
            "taken_at": taken, "year": int(y) if str(y or "").isdigit() else None,
            **{k: (r.get(k) or None) for k in RICH},
            "people": sorted(people.get(h, ())),
            "day_key": days.get(h),
            "width": r.get("_w"), "height": r.get("_h"),
            "embedding": "[" + ",".join(map(str, vectors[h])) + "]" if h in vectors else None,
            "source": "seed",
        })
    return rows


def face_key(r: dict) -> str:
    return "{}:{}:{}".format(r["hash"], r.get("image") or "", r["face_index"])


def frame_ok(verdict: dict) -> bool:
    """A video frame is shown only with its OWN verdict, and only if it clears
    the same nudity rule as a photograph."""
    return bool(verdict.get("nudity")) and nudity_hold("none", verdict, False) == ""


def build(a, size_of=None, log=print) -> dict:
    size_of = size_of or BG._image_size
    db = open_ro(a.db)
    try:
        shared, held = share_set(db, blocked_hashes())
        sides = {h: side_of(p) for h, p in db.execute(
            "SELECT hash, path FROM files WHERE hash IS NOT NULL AND hash != ''")}
        log("share set: {:,} shared, {:,} held out".format(len(shared), sum(held.values())))
        md5s = mirror_md5(a.mirror)
        vectors = load_vectors(a.vectors, set(shared)) if os.path.isdir(a.vectors) else {}
        days = day_keys(a.events, set(shared))
        photos = photo_rows(db, shared, md5s, vectors, days)
    finally:
        db.close()
    log("photos: {:,}  with md5 {:,}  with embedding {:,}  in a day {:,}".format(
        len(photos), sum(1 for p in photos if p["md5"]),
        sum(1 for p in photos if p["embedding"]), sum(1 for p in photos if p["day_key"])))

    group_of, groups = BG.load_groups(a.merges, a.assign, a.video_assign)
    names = journal_names(a.answers, group_of)
    allowed = set(shared)

    # cluster -> group -> shared hashes: what the instant name overlay reaches
    ch, clusters = set(), {}
    for g, faces in groups.items():
        for r in faces:
            if r["hash"] in allowed:
                ch.add((r["cluster"], g, r["hash"]))
                clusters[r["cluster"]] = g
    family = {n for p in photos for n in p["people"]}

    per_image = collections.Counter((r["hash"], r.get("image") or "")
                                    for fs in groups.values() for r in fs)
    verdicts = {r["key"]: r for r in read_csv(a.frame_verdicts)}

    def usable(r):
        if r["hash"] not in allowed:
            return False
        return not r.get("image") or frame_ok(verdicts.get(face_key(r), {}))

    def face_row(r, path):
        wh = size_of(path) or (0, 0)
        x1, y1, x2, y2 = [float(v) for v in str(r["bbox"]).split(",")]
        if not wh[0] or not wh[1]:
            return None
        return {"key": face_key(r), "hash": r["hash"], "group_id": group_of.get(r["cluster"], r["cluster"]),
                "bbox": [round(x1 / wh[0], 5), round(y1 / wh[1], 5), round(x2 / wh[0], 5), round(y2 / wh[1], 5)],
                "only_face": per_image[(r["hash"], r.get("image") or "")] == 1,
                "frame": "frames/{}_{}.jpg".format(r["hash"], r["image"]) if r.get("image") else None,
                "score": float(r.get("det_score") or 0), "_path": path}

    faces, queue, frames = {}, [], {}
    known = PS.known_clusters(a.tags)
    verdict = BG.verdicts(a.answers, group_of) if os.path.exists(a.answers) else {}
    ranked = BG.select_queue(groups, verdict, known, sides, communal=True,
                             handed_to="bharti", allowed=allowed)
    for g, fs in ranked:
        if len(queue) >= a.max_queue:
            break
        picked = [face_row(r, p) for r, p in BG.pick_faces(
            [r for r in fs if usable(r)], a.thumbs, a.frames, PS.SUBJECT_SHARE, size_of)]
        picked = [f for f in picked if f]
        if not picked:
            continue
        hero = next((f for f in picked if f["only_face"]), picked[0])
        samples = [f for f in picked if f["key"] != hero["key"]][:SAMPLES]
        for f in [hero] + samples:
            faces[f["key"]] = f
        queue.append({"group_id": g, "rank": len(queue),
                      "photo_count": len({r["hash"] for r in fs}),
                      "hero_face": hero["key"], "sample_faces": [f["key"] for f in samples]})

    # a cover face per family member, from a shared photograph only
    covers = {}
    for g, fs in groups.items():
        n = names.get(g)
        if not n or n not in family:
            continue
        for r in sorted(fs, key=lambda x: -float(x.get("det_score") or 0)):
            if r["hash"] in allowed and not r.get("image"):
                p = os.path.join(a.thumbs, r["hash"][:2], r["hash"] + ".jpg")
                f = face_row(r, p)
                if f and (n not in covers or (f["only_face"] and not covers[n]["only_face"])):
                    covers[n] = f
                if n in covers and covers[n]["only_face"]:
                    break
    for f in covers.values():
        faces[f["key"]] = f
    counts = collections.Counter(n for p in photos for n in p["people"])
    people = [{"name": n, "cover_face": covers[n]["key"] if n in covers else None,
               "photo_count": counts[n]} for n in sorted(family)]

    suggest(a, queue, groups, group_of, names, family, covers, log)

    for f in faces.values():
        if f["frame"]:
            frames[f["frame"]] = f["_path"]
        f.pop("_path", None)

    players = []
    try:
        from guards.profile import load as load_profile
        prof = load_profile(required=False)
        if prof is not None:
            players = [{"name": str(n), "sort": i}
                       for i, n in enumerate((prof._d.get("app") or {}).get("players") or [])]
    except Exception as e:                                       # noqa: BLE001
        log("  (no players list: {})".format(e))

    bundle = {
        "photos": photos,
        "clusters": [{"cluster_id": c, "group_id": g, "name": names.get(g)} for c, g in clusters.items()],
        "cluster_hashes": [{"cluster_id": c, "group_id": g, "hash": h} for c, g, h in sorted(ch)],
        "faces": list(faces.values()),
        "people": people,
        "queue": queue,
        "players": players,
        "_frames": frames,
        "_held": dict(held),
    }
    log("clusters {:,}  queue {:,}  faces {:,}  people {:,}  video frames {:,}  players {:,}".format(
        len(bundle["clusters"]), len(queue), len(faces), len(people), len(frames), len(players)))
    unjudged = sum(1 for fs in groups.values() for r in fs
                   if r.get("image") and r["hash"] in allowed
                   and face_key(r) not in verdicts)
    if unjudged:
        log("  {:,} video faces have no frame verdict and are NOT used - "
            "run --check-frames to judge them".format(unjudged))
    return bundle


def suggest(a, queue, groups, group_of, names, family, covers, log):
    """Up to four family names whose face centroid is nearest, each with a face.

    Embeddings are read from the rows that carry them, joined on (hash,
    face_index) for photographs and (image, face_index) for video - learning
    45: a positional cache drifted until 11,347 vectors described the wrong
    face while every count agreed.
    """
    import base64
    import numpy as np
    by_photo = {(r["hash"], r["face_index"]): r["cluster"] for fs in groups.values()
                for r in fs if not r.get("image")}
    by_video = {(r["image"], r["face_index"]): r["cluster"] for fs in groups.values()
                for r in fs if r.get("image")}
    sums, n = {}, collections.Counter()
    for path, key in ((a.faces, lambda r: by_photo.get((r.get("hash"), r.get("face_index")))),
                      (a.video_faces, lambda r: by_video.get((r.get("image"), r.get("face_index"))))):
        for r in read_csv(path):
            c = key(r)
            if not c or not r.get("emb"):
                continue
            g = group_of.get(c, c)
            v = np.frombuffer(base64.b64decode(r["emb"]), dtype=np.float16).astype(np.float32)
            sums[g] = sums.get(g, 0) + v
            n[g] += 1
    if not sums:
        log("  no face embeddings found - queue has no suggestions")
        return
    cent = {g: v / (np.linalg.norm(v) or 1.0) for g, v in sums.items()}
    named = [(names[g], cent[g]) for g in cent if names.get(g) in family and names[g] in covers]
    if not named:
        return
    best = {}
    for name, v in named:                    # one centroid per NAME: a person may span groups
        best.setdefault(name, []).append(v)
    labels = list(best)
    M = np.stack([np.mean(best[k], axis=0) / (np.linalg.norm(np.mean(best[k], axis=0)) or 1.0)
                  for k in labels])
    for q in queue:
        v = cent.get(q["group_id"])
        if v is None:
            q["suggestions"] = []
            continue
        sims = M @ v
        order = np.argsort(-sims)[:4]
        q["suggestions"] = [{"name": labels[i], "face": covers[labels[i]]["key"],
                             "score": round(float(sims[i]), 3)}
                            for i in order if sims[i] >= SUGGEST_MIN]


def check_frames(a, log=print) -> int:
    """Judge every video face frame that could be shown, once, and cache it."""
    import classify_live as CL
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        log("STOPPING: GOOGLE_API_KEY is not set")
        return 1
    db = open_ro(a.db)
    try:
        shared, _ = share_set(db, blocked_hashes())
    finally:
        db.close()
    done = {r["key"] for r in read_csv(a.frame_verdicts)}
    _, groups = BG.load_groups(a.merges, a.assign, a.video_assign)
    todo = {}
    for fs in groups.values():
        for r in fs:
            if r.get("image") and r["hash"] in shared and face_key(r) not in done:
                todo[face_key(r)] = os.path.join(a.frames, r["hash"][:2], r["image"] + ".jpg")
    log("video face frames to judge: {:,}".format(len(todo)))
    new = not os.path.exists(a.frame_verdicts)
    with io.open(a.frame_verdicts, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["key", "nudity", "subject_age", "sexual", "note"])
        for i, (k, p) in enumerate(todo.items()):
            if not os.path.exists(p):
                continue
            try:
                txt, _, _ = CL.call([p], key, prompt=CL.SENS_PROMPT, max_out=200)
                v = CL.parse(txt)
            except Exception as e:                               # noqa: BLE001
                log("  {} : {}".format(k, e))
                continue
            w.writerow([k, v.get("nudity", ""), v.get("subject_age", ""),
                        v.get("sexual", ""), (v.get("nudity_note") or "")[:60]])
            fh.flush()
            if i % 200 == 0:
                log("  {:,} / {:,}".format(i, len(todo)))
    return 0


def upload(a, bundle: dict, log=print) -> int:
    from cloud import Cloud
    c = Cloud()
    # watermark FIRST: the newest app answer the journal already holds
    ing = c.select("answers", "select=at&status=eq.ingested&order=at.desc&limit=1")
    watermark = ing[0]["at"] if ing else None

    have = {r["hash"] for r in c.select("photos", "select=hash&source=eq.seed")}
    keep = {p["hash"] for p in bundle["photos"]}
    gone = sorted(have - keep)
    # drive_id and hidden are NOT in the payload, so an upsert keeps them
    c.upsert("photos", bundle["photos"], "hash")
    if gone:
        c.delete_in("photos", "hash", gone)
    log("photos: {:,} upserted, {:,} removed (left the share set)".format(len(keep), len(gone)))

    for path_key, local in bundle["_frames"].items():
        with open(local, "rb") as fh:
            c.put_object(path_key, fh.read())
    log("video frames uploaded: {:,}".format(len(bundle["_frames"])))

    for t, col in (("queue", "group_id"), ("people", "name"), ("faces", "key"),
                   ("cluster_hashes", "hash"), ("clusters", "cluster_id"), ("players", "name")):
        c.delete_all(t, col)
    c.upsert("clusters", bundle["clusters"], "cluster_id")
    c.upsert("cluster_hashes", bundle["cluster_hashes"], "cluster_id,hash")
    c.upsert("faces", bundle["faces"], "key")
    c.upsert("people", bundle["people"], "name")
    c.upsert("queue", bundle["queue"], "group_id")
    if bundle["players"]:
        c.upsert("players", bundle["players"], "name")

    # verify against the cloud's own count, not this script's
    got = len(c.select("photos", "select=hash&source=eq.seed"))
    ok = got == len(keep)
    c.insert("snapshots", {"kind": "seed", "watermark": watermark, "head": _head(),
                           "counts": {"photos": len(keep), "cloud_photos": got,
                                      "removed": len(gone), "queue": len(bundle["queue"]),
                                      "people": len(bundle["people"]),
                                      "held": bundle["_held"]}})
    log("receipt written. cloud holds {:,} seeded photos, expected {:,}: {}".format(
        got, len(keep), "OK" if ok else "MISMATCH"))
    return 0 if ok else 1


def _head() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=_d, text=True).strip()
    except Exception:                                            # noqa: BLE001
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    for k, v in DEFAULTS.items():
        ap.add_argument("--" + k.replace("_", "-"), dest=k, default=v)
    ap.add_argument("--max-queue", type=int, default=MAX_QUEUE)
    ap.add_argument("--check-frames", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print("STOPPING: no index at {}".format(a.db))
        return 1
    if a.check_frames:
        return check_frames(a)
    bundle = build(a)
    os.makedirs(a.out, exist_ok=True)
    for t, rows in bundle.items():
        if not t.startswith("_"):
            with io.open(os.path.join(a.out, t + ".json"), "w", encoding="utf-8") as fh:
                json.dump(rows, fh)
    print("bundle written to {} (it holds family names: it stays on this machine)".format(a.out))
    if not a.apply:
        print("dry run - nothing uploaded. Re-run with --apply.")
        return 0
    return upload(a, bundle)


if __name__ == "__main__":
    sys.exit(main())
