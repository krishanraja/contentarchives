r"""Carry everything the library learned about the Communal photographs to the
cloud ONCE. Read-only on the library; dry by default.

    python stages/13_app/export_library.py                  # counts only
    python stages/13_app/export_library.py --write          # build the file

Krish, 2026-10-05: *"make it such that this is never reliant on a local machine
or external drive again"*. The photographs are already on Google Drive. What
Drive has never held is the knowledge: 85,000 descriptions, the places, the
dates, the face groups, who is who, and every answer Krish and Bharti gave. It
lives in `library.db`, `_enrichment` and the answers journal on this machine's
drives, and after this export it lives in Supabase and is never read from a
local drive again.

The format, the rules and what the cloud does with the file are
`stages/13_app/LIBRARY-EXPORT.md`. This script is one of its two writers; the
other is `cloud_enrich.py`, which imports the file. Read the contract before
changing either.

WHAT IS REUSED, AND WHY NOTHING IS RE-DECIDED HERE

Every decision this export makes was already made somewhere in the conveyor,
and a second implementation of any of them is a second rule that drifts:

  `share_set.share_set`   what may leave this machine. `photos` IS its shared
                          set, with no filter of our own added or removed. It
                          is called with `reasons=` so the held-out files can
                          be NAMED in `held`, not merely counted - the counts
                          it already returned cannot tell the cloud which file
                          to keep out
  `share_set.open_ro`     read-only, closed promptly (learning 55)
  `seed_index.mirror_md5` blake2b -> md5: how a row finds its Drive file
  `seed_index.load_vectors` description vectors, joined on HASH
  `seed_index.day_keys`   EVENTS.json, explicit hashes per event
  `seed_index.photo_rows` the photo columns, straight from `resolved`
  `seed_index.rel_path`   the path the same file has under ContentLibrary
  `build_game.load_groups` clusters, and CLUSTER-MERGES.csv applied
  `build_game._image_size` the thumbnail a bbox was measured against
  `people_sheet.is_subject`'s formula for `share`, via `face_share()`

JOINED BY KEY, NEVER BY POSITION (learning 45)

Face embeddings are read from the rows that carry them and joined on
(hash, face_index) for photographs and (image, face_index) for video frames;
description vectors join on hash. A positional cache once drifted until 11,347
vectors described the wrong face while every count agreed, so the two CSVs here
are read into dicts keyed the same way `suggest()` keys them, and a face with
no embedding of its own is DROPPED and counted, never given a neighbour's.

HELD OUT STAYS HELD OUT

`held` names every file under `Media\Communal` that the share rules keep out,
plus every purged hash whose md5 is known - a purged photograph still sitting
on Drive must arrive at the cloud as held, or the cloud will classify it and
show it. Membership is "has a copy under Media\Communal and is not shared",
which is wider than `path_ok()` on purpose: a file at
`Media\Communal\...\Intimate\x.jpg` fails `path_ok` and is still inside Drive's
Communal tree, so the cloud must be told about it. A hash with no Communal copy
at all (Personal, Archive, `_Review`) is not on that side of Drive and is
written NOWHERE, not even as held.

`reason` is a CATEGORY WORD, never a description: the export carries family
faces into a place a description of the content would not belong.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import io
import json
import os
import sqlite3
import struct
import sys
import uuid

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import paths as P                                                # noqa: E402
import build_game as BG                                          # noqa: E402
from blocklist import blocked_hashes, BLOCKLIST                   # noqa: E402
from share_set import share_set, open_ro, SHARED_ROOT, _norm      # noqa: E402
from seed_index import (read_csv, rel_path, mirror_md5, load_vectors,
                        day_keys, photo_rows, face_key)           # noqa: E402

FORMAT = "1"
DESC_DIM, FACE_DIM = 768, 512
OUT = r"H:\My Drive\Archives-Library\archives-library.sqlite"

# The library machine's stores. P.AUDIT is the definition; a drive that has been
# reassigned (the external library answered to D: and now answers to F:) is
# found here rather than by editing paths.py, because paths.py is the whole
# conveyor's root and this export is read-only on all of it. An absent store is
# NOT an empty one (learning 34): if none of these holds library.db the script
# stops instead of exporting zero rows.
AUDIT_ROOTS = [P.AUDIT, r"F:\_PhotoAudit", r"E:\_PhotoAudit"]
STORE_ROOTS = [r"D:\_enrichment", r"F:\_enrichment", r"E:\_enrichment"]

SCHEMA = """
create table meta (key text primary key, value text);

create table photos (
  hash        text primary key,
  md5         text,
  rel_path    text not null,
  media       text not null,
  taken_at    text, year int, approx_year text,
  place text, region text, country text,
  description text, objects text, activity text, occasion text, mood text,
  people      text not null default '[]',
  day_key     text,
  width int, height int,
  embedding   blob
);

create table held (
  hash text primary key, md5 text, rel_path text,
  reason text not null
);

create table clusters (
  cluster_id text primary key,
  group_id   text not null
);

create table faces (
  key        text primary key,
  hash       text not null,
  image      text not null default '',
  face_index int  not null,
  cluster_id text not null,
  x1 real, y1 real, x2 real, y2 real,
  thumb_w int, thumb_h int,
  det   real,
  share real,
  only_face int not null,
  embedding blob not null
);

create table answers (
  id     text primary key,
  at     text not null,
  who    text not null,
  scope  text not null,
  target text not null,
  field  text not null, value text not null,
  confidence real, note text
);

create index photos_md5 on photos (md5);
create index held_md5 on held (md5);
create index faces_hash on faces (hash);
create index faces_cluster on faces (cluster_id);
create index answers_target on answers (target);
"""

# share_set's reasons are sentences a human reads in a report. `held.reason` is
# a category word the cloud groups by, so each sentence maps to one word here.
# The mapping NEVER changes a decision: everything in this table is already
# held, and a reason that is not in it still lands in `held`, under 'other'.
REASON_WORDS = (
    ("a copy lives outside", "outside-communal"),
    ("purged", "removed"),
    ("audience is not family", "audience"),
    ("Krish said do not share", "withheld"),
    ("never classified for sensitivity", "unclassified"),
    ("sensitivity is intimate", "intimate"),
    ("the nudity pass says sexual", "sexual"),
    ("nudity with an adult or unclear age", "nudity"),
    ("nudity verdict not understood", "nudity"),
    ("private-family with no nudity verdict", "nudity"),
    ("sensitivity is ", "sensitive"),
)


def reason_word(why: str) -> str:
    """One category word for one of share_set's held-out reasons."""
    if why.startswith("not a photograph ("):
        kind = why[len("not a photograph ("):-1].strip()
        return kind.replace(" ", "-") if kind and kind != "no kind" else "no-kind"
    for prefix, word in REASON_WORDS:
        if why.startswith(prefix):
            return word
    return "other"


def _root(candidates: list, marker: str) -> str:
    for r in candidates:
        if os.path.exists(os.path.join(r, marker)):
            return r
    return candidates[0]


AUDIT = _root(AUDIT_ROOTS, "library.db")
STORE = _root(STORE_ROOTS, "answers.csv")
DEFAULTS = {
    "db": os.path.join(AUDIT, "library.db"),
    "assign": os.path.join(AUDIT, "FACE-CLUSTERS.csv"),
    "video_assign": os.path.join(AUDIT, "FACE-CLUSTERS-VIDEO.csv"),
    "merges": os.path.join(AUDIT, "CLUSTER-MERGES.csv"),
    "vectors": os.path.join(AUDIT, "desc-vectors"),
    "events": os.path.join(AUDIT, "EVENTS.json"),
    "mirror": os.path.join(AUDIT, "h-mirror.csv"),
    "blocklist": os.path.join(AUDIT, os.path.basename(BLOCKLIST)),
    "answers": os.path.join(STORE, "answers.csv"),
    "faces": os.path.join(STORE, "faces.0.csv"),
    "video_faces": os.path.join(STORE, "faces.video.csv"),
    "thumbs": r"D:\_thumbs" if os.path.isdir(r"D:\_thumbs") else r"F:\_thumbs",
    "out": OUT,
}


# --- the pieces the schema needs that nothing else already builds -----------

def vec_blob(vec, dim: int) -> bytes:
    """float32 little-endian, unit length, exactly `dim` wide.

    Unit length is re-asserted here because `load_vectors` rounds to six
    decimals for the JSON seed: the rounding moves the norm by about 1e-6,
    which is invisible in a cosine and is still not 1.0, and the cloud checks.
    """
    import numpy as np
    v = np.asarray(vec, dtype="float32")
    if v.shape != (dim,):
        raise ValueError("expected {} floats, got {}".format(dim, v.shape))
    v = v / (float(np.linalg.norm(v)) or 1.0)
    return struct.pack("<{}f".format(dim), *v.astype("float32").tolist())


def face_embeddings(photo_csv: str, video_csv: str, wanted: set) -> dict:
    """(hash, face_index) / (image, face_index) -> the 512 floats of THAT face.

    Learning 45: joined on the key the row carries, never on its position. The
    photograph rows key on (hash, face_index) and the video rows on (image,
    face_index) - a frame key is unique across videos, and the same hash holds
    many frames, so hash is not the key on that side.
    """
    import base64
    import numpy as np
    out = {}
    for path, key in ((photo_csv, lambda r: (r.get("hash"), r.get("face_index"))),
                      (video_csv, lambda r: (r.get("image"), r.get("face_index")))):
        for r in read_csv(path):
            k = key(r)
            if not r.get("emb") or k not in wanted:
                continue
            v = np.frombuffer(base64.b64decode(r["emb"]), dtype=np.float16).astype("float32")
            if v.shape == (FACE_DIM,):
                out[k] = v
    return out


def face_share(bbox, thumb) -> float:
    """people_sheet.is_subject's measure, as a number rather than a verdict:
    the face's short edge over the thumbnail's, in the pixels the box was
    measured in."""
    x1, y1, x2, y2 = bbox
    short = min(thumb) if thumb and min(thumb) > 0 else 0
    return (min(x2 - x1, y2 - y1) / float(short)) if short else None


def answer_id(r: dict) -> str:
    """The contract's id: uuid5 over the row's own content, so re-exporting the
    same journal row is the same row and never a second one."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "journal:" + "|".join(
        (r.get(k) or "") for k in ("when", "who", "scope", "target", "field", "value"))))


def _num(v, cast):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


# --- the build ---------------------------------------------------------------

def build(a, size_of=None, log=print) -> dict:
    """Every table of the export, as lists of tuples in schema column order."""
    size_of = size_of or BG._image_size
    db = open_ro(a.db)
    try:
        purged = blocked_hashes(a.blocklist)
        reasons = {}
        shared, held_counts = share_set(db, purged, reasons)
        log("share set: {:,} shared, {:,} held out".format(
            len(shared), sum(held_counts.values())))
        # every path of every hash, for the held rows and the Communal test
        all_paths = collections.defaultdict(list)
        for path, h in db.execute("SELECT path, hash FROM files "
                                  "WHERE hash IS NOT NULL AND hash != ''"):
            all_paths[h].append(path)
        md5s = mirror_md5(a.mirror, log)
        vectors = load_vectors(a.vectors, set(shared)) if os.path.isdir(a.vectors) else {}
        days = day_keys(a.events, set(shared))
        rows = photo_rows(db, shared, md5s, vectors, days)
    finally:
        db.close()

    photos = []
    for p in rows:
        rp = p["rel_path"].replace("\\", "/")
        if not rp.lower().startswith("media/communal/"):
            raise SystemExit(
                "STOPPING: a shared row's path is not under Media/Communal. "
                "share_set and rel_path disagree, and guessing which is right "
                "is how something private ships.")
        photos.append((
            p["hash"], p["md5"], rp, p["media"], p["taken_at"], p["year"],
            p["approx_year"], p["place"], p["region"], p["country"],
            p["description"], p["objects"], p["activity"], p["occasion"],
            p["mood"], json.dumps(p["people"]), p["day_key"],
            p["width"], p["height"],
            vec_blob(vectors[p["hash"]], DESC_DIM) if p["hash"] in vectors else None,
        ))
    log("photos: {:,}  with md5 {:,}  with embedding {:,}  in a day {:,}".format(
        len(photos), sum(1 for p in photos if p[1]),
        sum(1 for p in photos if p[-1]), sum(1 for p in photos if p[16])))

    # held: a Communal copy and not shared, plus every purged hash we can name
    held, held_by_reason = [], collections.Counter()
    for h, why in sorted(reasons.items()):
        communal = sorted(p for p in all_paths.get(h, ())
                          if SHARED_ROOT in _norm(p))
        if not communal:
            continue                 # not on Drive's Communal side at all
        word = "removed" if h.lower() in purged else reason_word(why)
        held.append((h, md5s.get(h.lower()), rel_path(communal[0]).replace("\\", "/"), word))
        held_by_reason[word] += 1
    named = {r[0] for r in held}
    for h in sorted(purged):
        if h not in named and md5s.get(h):
            held.append((h, md5s[h], None, "removed"))
            held_by_reason["removed"] += 1
    log("held: {:,}  ({})".format(len(held), ", ".join(
        "{} {:,}".format(w, n) for w, n in held_by_reason.most_common())))

    # clusters and faces
    group_of, groups = BG.load_groups(a.merges, a.assign, a.video_assign)
    allowed = set(shared)
    face_rows = [r for fs in groups.values() for r in fs if r["hash"] in allowed]
    per_image = collections.Counter((r["hash"], r.get("image") or "")
                                    for r in face_rows)
    clusters = sorted({(r["cluster"], group_of.get(r["cluster"], r["cluster"]))
                       for r in face_rows})

    wanted = set()
    for r in face_rows:
        wanted.add((r["image"], r["face_index"]) if r.get("image")
                   else (r["hash"], r["face_index"]))
    embs = face_embeddings(a.faces, a.video_faces, wanted)
    log("faces on exported photographs: {:,}  with an embedding {:,}".format(
        len(face_rows), len(embs)))

    faces, sizes, no_emb, no_box = [], {}, 0, 0
    for r in face_rows:
        image = r.get("image") or ""
        k = (image, r["face_index"]) if image else (r["hash"], r["face_index"])
        if k not in embs:
            no_emb += 1
            continue
        box = thumb = b = None
        if not image:
            # the bbox is in the pixels of the THUMBNAIL it was measured on
            tp = os.path.join(a.thumbs, r["hash"][:2], r["hash"] + ".jpg")
            if tp not in sizes:
                sizes[tp] = size_of(tp)
            thumb = sizes[tp]
            try:
                b = [float(v) for v in str(r["bbox"]).split(",")]
            except ValueError:
                b = None
            if b and len(b) == 4 and thumb and thumb[0] and thumb[1]:
                box = [round(b[0] / thumb[0], 6), round(b[1] / thumb[1], 6),
                       round(b[2] / thumb[0], 6), round(b[3] / thumb[1], 6)]
            else:
                no_box += 1
        faces.append((
            face_key(r), r["hash"], image, int(r["face_index"]),
            r["cluster"],
            box[0] if box else None, box[1] if box else None,
            box[2] if box else None, box[3] if box else None,
            thumb[0] if thumb else None, thumb[1] if thumb else None,
            _num(r.get("det_score"), float),
            round(face_share(b, thumb), 6) if box else None,
            1 if per_image[(r["hash"], image)] == 1 else 0,
            vec_blob(embs[k], FACE_DIM),
        ))
    log("faces: {:,} exported  ({:,} dropped with no embedding of their own, "
        "{:,} photo faces have no usable box)".format(len(faces), no_emb, no_box))

    # the journal, verbatim, oldest first, for exported targets only
    targets = allowed | {c for c, _ in clusters}
    answers, by_field, seen = [], collections.Counter(), set()
    for r in read_csv(a.answers):
        if (r.get("target") or "") not in targets:
            continue
        i = answer_id(r)
        if i in seen:
            continue
        seen.add(i)
        answers.append((i, r.get("when") or "", r.get("who") or "",
                        r.get("scope") or "", r["target"], r.get("field") or "",
                        r.get("value") or "", _num(r.get("confidence"), float),
                        r.get("note") or None))
        by_field[r.get("field") or ""] += 1
    log("answers: {:,}  ({})".format(len(answers), ", ".join(
        "{} {:,}".format(f, n) for f, n in by_field.most_common())))

    counts = {"photos": len(photos), "held": len(held), "clusters": len(clusters),
              "faces": len(faces), "answers": len(answers)}
    meta = [("format", FORMAT),
            ("created_at", dt.datetime.now(dt.timezone.utc)
             .strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("repo_head", _head()),
            ("counts", json.dumps(counts, sort_keys=True))]
    return {"meta": meta, "photos": photos, "held": held, "clusters": clusters,
            "faces": faces, "answers": answers,
            "_counts": counts, "_held_by_reason": dict(held_by_reason),
            "_share_held": dict(held_counts), "_by_field": dict(by_field),
            "_groups": len({g for _, g in clusters}),
            "_face_media": dict(collections.Counter(
                "video" if f[2] else "photo" for f in faces)),
            "_faces_with_box": sum(1 for f in faces if f[5] is not None)}


COLUMNS = {
    "meta": 2, "photos": 20, "held": 4, "clusters": 2, "faces": 15, "answers": 9,
}


def write(bundle: dict, out: str, log=print) -> int:
    """Atomic: a `.partial`, verified, then renamed, so Drive never syncs half
    a file (rule 6)."""
    part = out + ".partial"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    for stale in (part,):
        if os.path.exists(stale):
            os.remove(stale)
    db = sqlite3.connect(part)
    try:
        db.executescript(SCHEMA)
        for table, n in COLUMNS.items():
            db.executemany("insert or replace into {} values ({})".format(
                table, ",".join("?" * n)), bundle[table])
        db.commit()
        for table in COLUMNS:
            got = db.execute("select count(*) from " + table).fetchone()[0]
            if got != len(bundle[table]):
                raise SystemExit("STOPPING: {} holds {:,}, built {:,}".format(
                    table, got, len(bundle[table])))
    finally:
        db.close()
    os.replace(part, out)   # one rename, never a delete then a copy
    log("wrote {} ({:,} bytes)".format(out, os.path.getsize(out)))
    return 0


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
    ap.add_argument("--write", action="store_true",
                    help="build the export file; without it, counts only")
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print("STOPPING: no index at {} - an absent store is not an empty one "
              "(learning 34)".format(a.db))
        return 1
    bundle = build(a)
    c = bundle["_counts"]
    print()
    print("photos {photos:,}  held {held:,}  clusters {clusters:,}  "
          "faces {faces:,}  answers {answers:,}".format(**c))
    print("faces by media: {}  with a box: {:,}".format(
        bundle["_face_media"], bundle["_faces_with_box"]))
    print("groups: {:,}".format(bundle["_groups"]))
    if not a.write:
        print()
        print("dry run - nothing written. Re-run with --write.")
        return 0
    return write(bundle, a.out)


if __name__ == "__main__":
    sys.exit(main())
