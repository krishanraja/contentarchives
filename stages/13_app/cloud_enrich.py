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

THE LIBRARY, ONCE (Krish, 2026-10-05: "never reliant on a local machine or
external drive again")

Everything the library machine learned about these photographs - descriptions,
places, dates, faces, the merge groups people decided, every answer in the
journal - arrives ONCE as archives-library.sqlite (stages/13_app/
LIBRARY-EXPORT.md), a file in Krish's Drive shared with this account alone. It
is imported once per distinct file; after that this database is the system of
record and nothing reads a local drive again.

  - a library photo binds to its Drive file by MD5. By path only when the
    library knew no md5: a file whose bytes changed under the same name is a
    different file, and is judged afresh rather than inheriting a verdict
  - held is safety: a Drive file matching anything the library held out is held
    without being classified, shown or re-judged, now and whenever it reappears
    (library_held), and it wins every tie
  - a library row replaces a cloud-classified row for the same file; a second
    copy of a library photograph is held as a duplicate, never classified
  - a library row whose file leaves Drive is unbound, not deleted: what the
    library knew is kept, and it re-binds when the file comes back
  - the library's merge groups are pinned: the cloud never merges two of them,
    and its own clusters may join one
  - the journal is kept whole (`journal`), and its cluster answers flow through
    `answers` like the app's own. "needs_identifying" means "ask someone else",
    so it keeps a face IN the queue, first
  - a face is drawn only with a box measured on a picture the shape Drive
    shows; video faces and box-less faces group and find people, and are never
    drawn

VIDEOS PLAY ONLY ONCE ALL OF THEM HAS BEEN JUDGED (Krish, 2026-10-06)

A video was shown as one still, and only that still had been judged. Playing it
shows every frame, so videos() has the library's sensitivity pass watch the
whole video first (--videos per run, 0 by default: it is a spend), and the
most revealing moment decides by the same nudity_hold rule as a photograph. A
video that fails is hidden everywhere. Migration 0009 has the states.

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
import hashlib
import io
import json
import os
import random
import re
import shutil
import sqlite3
import struct
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
FRAME_PX, FRAME_MATCH = 960, 0.50          # a video frame's size; the same person, found again in it
PERSONAL_PREFIX = "Media/Personal"       # where the owner's own photographs sit, beside Communal
PERSONAL_SHARE = 0.08                      # a face this big (of the short side) is clearly in the photograph
VIDEO_SEGMENT = 20 * 60                    # seconds per look: a long tape is watched in parts that fit the model
VIDEO_MAX_BYTES = 2_000_000_000            # the Gemini File API's ceiling for one file
VIDEO_TRIES = 3                            # an unjudged video is tried again on this many runs
# Containers no phone's browser plays, known from Drive before a byte is downloaded
UNPLAYABLE_MIME = {"video/mpeg", "video/x-msvideo", "video/avi", "video/x-ms-wmv", "video/x-ms-asf",
                   "video/x-flv", "video/3gpp", "video/3gpp2", "video/mp2t", "video/dv", "video/x-dv"}
BUNDLE_NAME, BUNDLE_FORMAT = "archives-library.sqlite", "1"     # LIBRARY-EXPORT.md
DESC_DIM, FACE_DIM = 768, 512
LIBRARY_FIELDS = ("person", "unidentifiable", "needs_identifying")
# The journal's 'when' is the library machine's local clock, written without a
# zone. That machine is in Brisbane, which keeps no daylight saving.
JOURNAL_TZ = dt.timezone(dt.timedelta(hours=10))
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


def frame_ok(v: dict) -> bool:
    """seed_index.frame_ok: a video frame is shown only with its OWN verdict,
    and only if it clears the same nudity rule as a photograph."""
    sens = {k: str(v.get(k) or "").lower() for k in ("nudity", "subject_age", "sexual")}
    return bool(sens["nudity"]) and nudity_hold("none", sens, False) == ""


def video_verdict(verdicts: list) -> tuple:
    """(status, reason) for a whole video from the verdicts on every part of
    it. The most revealing moment decides, by the photograph's own rule. A part
    the model would not look at is held - a filter that refuses is a signal,
    not a pass. A part answered with nothing readable is no verdict at all, so
    the video is tried again rather than shown."""
    if not verdicts:
        return "error", "not judged"
    if any(v.get("_blocked") for v in verdicts):
        return "held", "the model would not look"
    for v in verdicts:
        sens = {k: str(v.get(k) or "").lower() for k in ("nudity", "subject_age", "sexual")}
        if sens["nudity"]:
            why = nudity_hold("none", sens, False)
            if why:
                return "held", why
    if any(not str(v.get("nudity") or "") for v in verdicts):
        return "error", "no verdict"
    return "ok", ""


def segments(seconds) -> list:
    """The parts a video is watched in: [(None, None)] - all of it at once -
    when it is short enough or its length is unknown, else whole-second
    (start, end) spans of VIDEO_SEGMENT that cover every second."""
    if not seconds or seconds <= VIDEO_SEGMENT:
        return [(None, None)]
    s = int(-(-seconds // 1))
    return [(a, min(a + VIDEO_SEGMENT, s)) for a in range(0, s, VIDEO_SEGMENT)]


def probe(path: str) -> dict:
    """Container, picture codec and length, as ffprobe reads the file."""
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,format_name:stream=codec_type,codec_name", "-of", "json", path],
                       capture_output=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError("probe failed")
    j = json.loads(r.stdout or b"{}")
    fmt = j.get("format") or {}
    codec = next((s.get("codec_name") for s in j.get("streams") or [] if s.get("codec_type") == "video"), "")
    try:
        secs = float(fmt.get("duration"))
    except (TypeError, ValueError):
        secs = None
    return {"format": fmt.get("format_name") or "", "codec": codec or "", "seconds": secs}


def play_mime(p: dict):
    """What a phone's browser is told the video is, or None when it cannot
    play it. A QuickTime file holding H.264 or HEVC plays as MP4."""
    c, f = p["codec"], p["format"]
    if "mp4" in f or "mov" in f:
        return "video/mp4" if c in ("h264", "hevc", "vp9", "av1") else None
    if "webm" in f or "matroska" in f:
        return "video/webm" if c in ("vp8", "vp9", "av1") else None
    return None


def remux(src: str, dst: str, codec: str) -> None:
    """The picture alone, as an H.264 MP4: everything the check has to see,
    and no sound it would be charged for hearing. H.264 is copied as it is;
    anything else (an iPhone's HEVC) is converted, no bigger than 1280px, so
    the model is never handed a picture it may not be able to decode."""
    import subprocess
    pic = (["-c:v", "copy"] if codec == "h264" else
           ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
            "-vf", "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"])
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
                        "-map", "0:v:0", *pic, "-an", "-f", "mp4", dst],
                       capture_output=True, timeout=3600)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) == 0:
        raise RuntimeError("remux failed")


# ------------------------------------------------------------ the world ----

class Drive:
    """Google Drive as the read-only service account. Sees Communal only."""
    FIELDS = ("nextPageToken, files(id, name, mimeType, md5Checksum, "
              "imageMediaMetadata(time, location, width, height, rotation), "
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
                                    "h": im.get("height") or vm.get("height"),
                                    "rot": im.get("rotation") or 0})
                token = j.get("nextPageToken") or ""
                if not token:
                    break
        return out

    def find(self, name: str):
        """The newest file of that name this account can see - which is only
        what has been shared with it: Communal, and the library export."""
        r = self.s.get("https://www.googleapis.com/drive/v3/files", params={
            "q": "name = '{}' and trashed = false".format(name.replace("'", "\\'")),
            "fields": "files(id, md5Checksum, size, modifiedTime)", "orderBy": "modifiedTime desc",
            "pageSize": 10, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}, timeout=60)
        r.raise_for_status()
        fs = r.json().get("files", [])
        return fs[0] if fs else None

    def download(self, fid: str, dest: str, md5: str = None) -> None:
        """The whole file, streamed to disk, checked against Drive's own md5."""
        h = hashlib.md5()
        with self.s.get("https://www.googleapis.com/drive/v3/files/" + fid,
                        params={"alt": "media", "supportsAllDrives": "true"},
                        stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    h.update(chunk)
        if md5 and h.hexdigest() != md5.lower():
            raise RuntimeError("download does not match Drive's md5")

    def frame(self, fid: str, ms: int, px: int = FRAME_PX):
        """ONE frame of a video on Drive, at `ms`, as a JPEG no wider than `px`.
        ffmpeg reads only the byte ranges it needs, so a two-hour tape is not
        downloaded to show one face. The token never reaches the log."""
        import subprocess
        import threading
        from google.auth.transport.requests import Request
        lock = self.__dict__.setdefault("_lock", threading.Lock())
        with lock:
            cr = self.s.credentials
            if not cr.valid:
                cr.refresh(Request())
            token = cr.token
        url = "https://www.googleapis.com/drive/v3/files/{}?alt=media&supportsAllDrives=true".format(fid)
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error",
               "-headers", "Authorization: Bearer {}\r\n".format(token),
               "-ss", "{:.3f}".format(ms / 1000.0), "-i", url, "-frames:v", "1",
               "-vf", "scale='min({},iw)':-2".format(px), "-q:v", "4", "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 and r.stdout[:2] == b"\xff\xd8" else None

    def meta(self, fid: str) -> dict:
        """A file's size and type, before deciding whether to download it."""
        r = self.s.get("https://www.googleapis.com/drive/v3/files/" + fid,
                       params={"fields": "size, mimeType", "supportsAllDrives": "true"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        return {"size": int(j.get("size") or 0), "mime": j.get("mimeType") or ""}

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


def err_name(e: Exception) -> str:
    """An error's kind for the public log: its type, and its HTTP status when it
    has one - never its message, which can carry a path or a description."""
    m = re.match(r"HTTP (\d{3})\b", str(e))
    return "http_" + m.group(1) if m else type(e).__name__


class Gemini:
    """The library's own classifier and embedder, priced at their own rates.

    ONE GATE FOR EVERY WORKER. The key's per-minute quota is shared by all the
    threads, and a rate limit is not a verdict: the first live frame run sent
    sixteen at once and lost 1,266 of 1,500 frames to refusals it treated as
    final. Calls now pass a small gate, and a refusal (429) or a server error
    (5xx) waits and tries again with growing pauses."""

    RETRY = re.compile(r"HTTP (429|500|502|503|504)\b")

    def __init__(self, key: str):
        import threading
        import classify_live as CL
        import embed_descriptions as ED
        self.CL, self.ED, self.key = CL, ED, key
        self.gate = threading.Semaphore(int(os.environ.get("GEMINI_CONCURRENCY", "4")))
        self.backoff = float(os.environ.get("GEMINI_BACKOFF", "5"))

    def _call(self, paths, prompt, max_out):
        return self._retry(lambda: self.CL.call(paths, self.key, prompt=prompt, max_out=max_out))

    def _retry(self, fn):
        delay = self.backoff
        for attempt in range(6):
            try:
                with self.gate:
                    return fn()
            except RuntimeError as e:
                if attempt == 5 or not self.RETRY.match(str(e)):
                    raise
            time.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, 60.0)

    def classify(self, jpeg: bytes):
        CL = self.CL
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            fh.write(jpeg)
            path = fh.name
        try:
            out, usd = {}, 0.0
            # the same output budgets classify_live.main() gives each pass
            for prompt, max_out in ((CL.PROMPT, 800), (CL.RICH_PROMPT, 1400), (CL.SENS_PROMPT, 200)):
                txt, tin, tout = self._call([path], prompt, max_out)
                usd += (tin * CL.IN_PER_M + tout * CL.OUT_PER_M) / 1e6
                out.update(CL.parse(txt))
            return out, usd
        finally:
            os.unlink(path)

    def sensitivity(self, jpeg: bytes):
        """The library's sensitivity pass alone (classify_live's SENS_PROMPT, its
        own output budget), for a video frame about to be shown."""
        CL = self.CL
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            fh.write(jpeg)
            path = fh.name
        try:
            txt, tin, tout = self._call([path], CL.SENS_PROMPT, 200)
            return CL.parse(txt), (tin * CL.IN_PER_M + tout * CL.OUT_PER_M) / 1e6
        finally:
            os.unlink(path)

    API = "https://generativelanguage.googleapis.com/"
    VIDEO_PROMPT = ("This is a video, not a photograph. Watch all of it, and answer for its MOST "
                    "revealing moment: if anyone is unclothed at any point, even briefly, say so.\n\n")
    poll = 5.0

    def video(self, path: str, seconds):
        """The library's sensitivity pass over the WHOLE of one video: uploaded
        once with the File API, watched in parts of VIDEO_SEGMENT (Gemini
        samples a frame a second), every part judged, the upload deleted
        whatever happens. -> (one verdict per part, dollars). The key travels
        in a header, never in an address that could be logged."""
        import requests
        http = getattr(self, "http", None) or requests
        CL, auth = self.CL, {"x-goog-api-key": self.key}

        def ok(r):
            if r.status_code >= 400:
                raise RuntimeError("HTTP {}: video".format(r.status_code))
            return r

        r = ok(http.post(self.API + "upload/v1beta/files", timeout=60, json={"file": {"display_name": "family-video"}},
                         headers={**auth, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                                  "X-Goog-Upload-Header-Content-Length": str(os.path.getsize(path)),
                                  "X-Goog-Upload-Header-Content-Type": "video/mp4"}))
        up = r.headers.get("x-goog-upload-url")
        if not up:
            raise RuntimeError("video upload: no upload address")
        with open(path, "rb") as fh:
            r = ok(http.post(up, data=fh, timeout=1800,
                             headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"}))
        f = (r.json() or {}).get("file") or {}
        name = f.get("name")
        if not name:
            raise RuntimeError("video upload: no file")
        try:
            t0 = time.time()
            while f.get("state") == "PROCESSING":
                if time.time() - t0 > 900:
                    raise RuntimeError("video still processing")
                time.sleep(self.poll)
                f = ok(http.get(self.API + "v1beta/" + name, headers=auth, timeout=60)).json() or {}
            if f.get("state") != "ACTIVE" or not f.get("uri"):
                raise RuntimeError("video upload not active")
            verdicts, usd = [], 0.0
            for a, b in segments(seconds):
                part = {"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}}
                if a is not None:
                    part["video_metadata"] = {"start_offset": "{}s".format(a), "end_offset": "{}s".format(b)}
                try:
                    txt, tin, tout = self._retry(lambda: CL.generate(
                        [part, {"text": self.VIDEO_PROMPT + CL.SENS_PROMPT}], self.key, 200, 600))
                except RuntimeError as e:
                    if str(e).startswith("BLOCKED"):
                        verdicts.append({"_blocked": True})
                        break                          # one refused part is enough to hold it
                    raise
                usd += (tin * CL.IN_PER_M + tout * CL.OUT_PER_M) / 1e6
                verdicts.append(CL.parse(txt))
            return verdicts, usd
        finally:
            try:
                http.delete(self.API + "v1beta/" + name, headers=auth, timeout=60)
            except Exception:                                    # noqa: BLE001
                pass                                             # Gemini deletes uploads after 48 hours anyway

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

def upright(f: dict):
    """(width, height) as Drive shows the picture: its stored size turned by the
    rotation Drive reports. None when Drive does not say."""
    w, h = f.get("w"), f.get("h")
    if not w or not h:
        return None
    return (int(h), int(w)) if int(f.get("rot") or 0) % 2 else (int(w), int(h))


def same_shape(a, b, tol: float = 0.03) -> bool:
    """The same aspect ratio within 3%: a thumbnail is the picture scaled, never
    cropped, so a box in fractions of one is a box in fractions of the other
    only when this holds."""
    import math
    return abs(math.log((a[0] / float(a[1])) / (b[0] / float(b[1])))) <= tol


def blob_vec(b: bytes, dim: int):
    """A float32 little-endian blob of exactly `dim`, or None."""
    import numpy as np
    if not b or len(b) != 4 * dim:
        return None
    return np.frombuffer(b, dtype="<f4").astype(np.float32)


def journal_time(when: str):
    """The journal's local, zone-less 'when' as an instant."""
    t = dt.datetime.fromisoformat(str(when).strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=JOURNAL_TZ)


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
                 budget=300, cap_usd=60.0, workers=8, max_minutes=None, frames=0, videos=0, personal=0):
        self.db, self.drive, self.gemini, self.faces, self.geo = db, drive, gemini, faces, geo
        self.folder, self.prefix = folder, prefix
        self.budget, self.cap, self.workers = budget, cap_usd, workers
        self.frames_per_run = frames
        self.videos_per_run = videos
        self.personal_per_run = personal
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

    def assign(self, emb, det, start=True):
        """-> cluster id, or None for a weak face that matches nobody. With
        start=False a face that matches nobody starts no cluster: a Personal
        photograph never puts a new face in front of the family."""
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
        if det < START or not start:
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
        rows = [(self.cid[j], self.cid[j], vec(self.C[j]), self.cn[j]) for j in sorted(self.dirty)]
        if rows:
            with self.db.cursor() as cur:            # one round trip, not one per cluster
                cur.executemany(
                    "insert into clusters (cluster_id, group_id, centroid, n) values (%s, %s, %s::extensions.vector, %s) "
                    "on conflict (cluster_id) do update set centroid = excluded.centroid, n = excluded.n", rows)
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
        pfolder = self.state("personal_folder")
        pfiles = self.drive.list_tree(pfolder, PERSONAL_PREFIX) if pfolder else None
        if pfiles is not None:
            self.c["personal_listed"] = len(pfiles)
            say("personal listed", files=len(pfiles))
        self.reconcile(files, pfiles)
        self.import_library()
        self.bind(files + (pfiles or []))
        self.load_clusters()
        self.personal_scan(pfiles or [])
        self.process(files + self.personal_wanted(pfiles or []))
        self.save_clusters()
        self.group()
        self.personal_show()                # after group(): a new face's group is known only then
        try:
            self.frames()                   # extra: its failure must not stop the rules and checks after it
        except Exception as e:              # noqa: BLE001
            self.db.rollback()
            self.errors["frames_" + err_name(e)] += 1
        self.private()
        self.videos()
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

    def private(self):
        """The owner's private rules (migration 0008), before anything is
        rebuilt: a photograph they cover is hidden before anyone can see it,
        and leaves the questions and the people's covers in the same run. The
        rules live only in the database - this repository is public."""
        h, s, c = self.db.execute("select * from apply_private_rules()").fetchone()
        self.db.commit()
        self.c["private_hidden"] = int(h)
        say("private", hidden=int(h), shown_again=int(s), covered=int(c))

    def reconcile(self, files, pfiles=None):
        """Each folder answers only for its own files: a Communal listing never
        removes a Personal photograph, and a Personal folder that is not listed
        this run (not set up, or not shared) removes nothing of its own."""
        rows = self.db.execute("select drive_id, rel_path from photos where drive_id is not null").fetchall()
        ours = PERSONAL_PREFIX + "/"
        for name, listing, known in (
                ("", files, [d for d, rel in rows if not (rel or "").startswith(ours)]),
                ("personal ", pfiles, [d for d, rel in rows if (rel or "").startswith(ours)])):
            if listing is None:
                continue
            ids = {f["id"] for f in listing}
            gone = [k for k in known if k not in ids]
            if not listing or (len(known) > 20 and len(gone) > len(known) * 0.2):
                if gone:
                    self.c[name.replace(" ", "_") + "refused_removal"] = len(gone)
                    say(name + "refused removal", gone=len(gone), known=len(known))
            elif gone:
                # what the cloud made is made again if the file returns; what the
                # LIBRARY knew can never be made again, so it is unbound, not lost
                self.db.execute("delete from photos where drive_id = any(%s) and source = 'cloud'", (gone,))
                self.db.execute("update photos set drive_id = null, updated_at = now() "
                                "where drive_id = any(%s) and source = 'seed'", (gone,))
                self.c[name.replace(" ", "_") + "removed"] = len(gone)
        if files:
            ids = [f["id"] for f in files]
            self.db.execute("delete from held where not (drive_id = any(%s)) and not (rel_path like %s)",
                            (ids, ours + "%"))
        if pfiles:
            ids = [f["id"] for f in pfiles]
            self.db.execute("delete from held where not (drive_id = any(%s)) and rel_path like %s",
                            (ids, ours + "%"))
            self.db.execute("delete from personal_seen where not (drive_id = any(%s))", (ids,))
        self.db.commit()

    # -- the library, once (LIBRARY-EXPORT.md) ---------------------------
    def state(self, key: str):
        r = self.db.execute("select value from sync_state where key = %s", (key,)).fetchone()
        return r[0] if r else None

    def set_state(self, key: str, value: str) -> None:
        self.db.execute("insert into sync_state (key, value) values (%s, %s) "
                        "on conflict (key) do update set value = excluded.value", (key, value))

    def import_library(self):
        """Import the library export once per distinct file. A file that is not
        what it says it is stops the run: half an import is worse than none."""
        if not hasattr(self.drive, "find"):
            return
        meta = self.drive.find(BUNDLE_NAME)
        if not meta:
            say("library export", found=0)
            return
        if meta.get("md5Checksum") and self.state("library_export") == meta["md5Checksum"]:
            say("library export", found=1, already_imported=1)
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "library.sqlite")
            self.drive.download(meta["id"], path, meta.get("md5Checksum"))
            src = sqlite3.connect("file:{}?mode=ro".format(path), uri=True)
            try:
                self.import_bundle(src)
            finally:
                src.close()
        self.set_state("library_export", meta.get("md5Checksum") or "")
        self.db.commit()

    def import_bundle(self, src) -> dict:
        db = self.db
        m = dict(src.execute("select key, value from meta").fetchall())
        if m.get("format") != BUNDLE_FORMAT:
            raise RuntimeError("library export is not format " + BUNDLE_FORMAT)
        n = {t: src.execute("select count(*) from " + t).fetchone()[0]
             for t in ("photos", "held", "clusters", "faces", "answers")}
        claimed = json.loads(m.get("counts") or "{}")
        bad = [t for t in n if t in claimed and int(claimed[t]) != n[t]]
        if bad:
            raise RuntimeError("library export counts disagree with its own meta")
        say("library export", photos=n["photos"], held=n["held"], clusters=n["clusters"],
            faces=n["faces"], answers=n["answers"])

        # held: kept for good, so a file that reaches Drive later is held unseen
        rows = []
        for h, md5, rel, why in src.execute("select hash, md5, rel_path, reason from held"):
            md5 = (md5 or "").lower() or None
            key = "md5:" + md5 if md5 else ("path:" + rel if rel else "hash:" + h)
            rows.append((key, h, md5, rel, why))
        with db.cursor() as cur:
            cur.executemany(
                "insert into library_held (key, hash, md5, rel_path, reason) values (%s,%s,%s,%s,%s) "
                "on conflict (key) do update set hash = excluded.hash, rel_path = excluded.rel_path, "
                "reason = excluded.reason", rows)
        db.commit()

        # photos: everything the library knew; drive_id and hidden are not
        # touched, so a binding and a person's "hide this" both survive
        cols = ("hash, md5, rel_path, media, taken_at, year, approx_year, place, region, country, "
                "description, objects, activity, occasion, mood, people, day_key, width, height, embedding")
        q = ("insert into photos (" + cols + ", source) values (" + ",".join(["%s"] * 19) +
             ", %s::extensions.vector, 'seed') on conflict (hash) do update set " +
             ", ".join("{0} = excluded.{0}".format(c.strip()) for c in cols.split(",")[1:-1]) +
             ", embedding = coalesce(excluded.embedding, photos.embedding), source = 'seed', updated_at = now()")
        batch, done = [], 0
        for r in src.execute("select " + cols + " from photos"):
            r = list(r)
            r[1] = (r[1] or "").lower() or None
            r[4] = r[4] or None
            try:
                r[15] = [str(x) for x in json.loads(r[15] or "[]")]
            except ValueError:
                r[15] = []
            v = blob_vec(r[19], DESC_DIM)
            r[19] = vec(v) if v is not None else None
            batch.append(r)
            if len(batch) >= 500:
                with db.cursor() as cur:
                    cur.executemany(q, batch)
                db.commit()
                done += len(batch)
                batch = []
        if batch:
            with db.cursor() as cur:
                cur.executemany(q, batch)
            db.commit()
            done += len(batch)
        self.c["library_photos"] = done

        # faces, the clusters they make, and the cluster -> photo map
        import numpy as np
        group_of = dict(src.execute("select cluster_id, group_id from clusters").fetchall())
        # a library box on a VIDEO was measured on the library's own frame grab,
        # not the frame Drive shows: kept for the record, never drawn
        videos = {h for (h,) in src.execute("select hash from photos where media = 'video'")}
        sums, cnt, ch = {}, collections.Counter(), set()
        fq = ("insert into faces (key, hash, cluster_id, group_id, bbox, only_face, score, share, "
              "measured_w, measured_h, embedding) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector) "
              "on conflict (key) do update set hash = excluded.hash, cluster_id = excluded.cluster_id, "
              "group_id = excluded.group_id, bbox = excluded.bbox, only_face = excluded.only_face, "
              "score = excluded.score, share = excluded.share, measured_w = excluded.measured_w, "
              "measured_h = excluded.measured_h, embedding = excluded.embedding")
        batch, done, boxed = [], 0, 0
        for (key, h, cid, x1, y1, x2, y2, tw, th, det, share, only, emb) in src.execute(
                "select key, hash, cluster_id, x1, y1, x2, y2, thumb_w, thumb_h, det, share, only_face, "
                "embedding from faces"):
            v = blob_vec(emb, FACE_DIM)
            if v is None:
                self.c["library_faces_bad"] += 1
                continue
            sums[cid] = sums[cid] + v if cid in sums else v.copy()
            cnt[cid] += 1
            g = group_of.get(cid, cid)
            ch.add((cid, g, h))
            box = [round(float(x), 5) for x in (x1, y1, x2, y2)] if None not in (x1, y1, x2, y2) else None
            boxed += box is not None
            batch.append((key, h, cid, g, box, bool(only), det,
                          share if box is not None and h not in videos else None,
                          tw if box is not None else None, th if box is not None else None, vec(v)))
            if len(batch) >= 1000:
                with db.cursor() as cur:
                    cur.executemany(fq, batch)
                db.commit()
                done += len(batch)
                batch = []
        if batch:
            with db.cursor() as cur:
                cur.executemany(fq, batch)
            db.commit()
            done += len(batch)
        self.c["library_faces"] = done
        self.c["library_faces_boxed"] = boxed

        crow = []
        for cid, g in group_of.items():
            if cid in sums:
                c = sums[cid] / (float(np.linalg.norm(sums[cid])) or 1.0)
                crow.append((cid, g, vec(c), int(cnt[cid])))
            else:
                crow.append((cid, g, None, 0))
        with db.cursor() as cur:
            cur.executemany(
                "insert into clusters (cluster_id, group_id, pinned, centroid, n) "
                "values (%s, %s, true, %s::extensions.vector, %s) on conflict (cluster_id) do update set "
                "group_id = excluded.group_id, pinned = true, "
                "centroid = coalesce(excluded.centroid, clusters.centroid), n = excluded.n", crow)
            cur.executemany(
                "insert into cluster_hashes (cluster_id, group_id, hash) values (%s, %s, %s) "
                "on conflict (cluster_id, hash) do update set group_id = excluded.group_id", sorted(ch))
        db.commit()
        self.c["library_clusters"] = len(crow)
        self.c["library_groups"] = len(set(group_of.values()))

        # the journal, whole; its cluster answers through `answers`
        jrows, arows = [], []
        for (aid, at, who, scope, target, field, value, conf, note) in src.execute(
                "select id, at, who, scope, target, field, value, confidence, note from answers order by rowid"):
            try:
                t = journal_time(at)
            except ValueError:
                self.c["journal_bad_time"] += 1
                continue
            jrows.append((aid, t, who or "?", scope, target, field, value, conf, note))
            if scope == "cluster" and field in LIBRARY_FIELDS and 1 <= len(value or "") <= 60:
                arows.append((aid, t, t, who or "?", scope, target, field, value))
        with db.cursor() as cur:
            cur.executemany(
                "insert into journal (id, at, who, scope, target, field, value, confidence, note) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (id) do nothing", jrows)
            cur.executemany(
                "insert into answers (id, at, client_at, who, scope, target, field, value, status, reason) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,'ingested','the library journal') on conflict (id) do nothing",
                arows)
        db.commit()
        self.c["library_journal"] = len(jrows)
        self.c["library_answers"] = len(arows)
        say("library imported", photos=self.c["library_photos"], faces=done, boxed=boxed,
            clusters=len(crow), journal=len(jrows), answers=len(arows))
        return n

    def bind(self, files):
        """Library rows -> their Drive files. Held first, because safety wins
        every tie; then each library photo by md5 (by path only when the library
        knew no md5); then second copies; then the faces' shape check.

        DECIDED IN MEMORY, WRITTEN IN A HANDFUL OF STATEMENTS. The database is in
        Sydney and the runner is not: a statement per row is a Pacific round trip
        per row, and binding 22,752 photos that way ran for over an hour."""
        db = self.db
        by_md5 = collections.defaultdict(list)
        for f in files:
            if f.get("md5"):
                by_md5[f["md5"].lower()].append(f)
        by_rel = {f["rel"]: f for f in files}
        held = dict(db.execute("select drive_id, reason from held").fetchall())
        owner = {d: (h, src) for d, h, src in db.execute(
            "select drive_id, hash, source from photos where drive_id is not null").fetchall()}
        seed = db.execute("select hash, lower(md5), rel_path, drive_id from photos "
                          "where source = 'seed'").fetchall()
        drop_cloud, let_go, new_held, binds = set(), set(), {}, {}

        def kind(fid):
            """Who holds this Drive file now: 'seed', 'cloud', or None."""
            return owner.get(fid, (None, None))[1]

        def take_from(fid):
            """Free a Drive file: a cloud row for it goes, a library row lets go."""
            h, src = owner.pop(fid, (None, None))
            if src == "cloud":
                drop_cloud.add(h)
                self.c["replaced"] += 1
            elif src == "seed":
                let_go.add(h)
                binds.pop(h, None)

        def hold(f, why):
            take_from(f["id"])
            new_held[f["id"]] = (f["rel"], why)
            held[f["id"]] = why

        for md5, rel, why in db.execute("select md5, rel_path, reason from library_held").fetchall():
            for f in (by_md5.get(md5, []) if md5 else ([by_rel[rel]] if rel in by_rel else [])):
                if held.get(f["id"]) != why:
                    hold(f, why)
                    self.c["held_library"] += 1

        for h, md5, rel, d in seed:
            if d is not None and h not in let_go:
                continue                                  # bound, and still is
            cands = by_md5.get(md5, []) if md5 else ([by_rel[rel]] if rel in by_rel else [])
            cands = [f for f in cands if f["id"] not in held and kind(f["id"]) in (None, "cloud")]
            if not cands:
                self.c["unbound"] += 1
                continue
            f = next((x for x in cands if x["rel"] == rel), sorted(cands, key=lambda x: x["rel"])[0])
            take_from(f["id"])
            owner[f["id"]] = (h, "seed")
            binds[h] = f
            let_go.discard(h)                             # bound again, to this file

        # a second copy of a library photograph is that photograph: never classified
        seed_md5 = {md5 for h, md5, _, d in seed
                    if md5 and (h in binds or (d is not None and h not in let_go))}
        for md5 in seed_md5:
            for f in by_md5.get(md5, []):
                if f["id"] not in held and kind(f["id"]) != "seed":
                    hold(f, "duplicate")
                    self.c["duplicates"] += 1

        # write: free first (drive_id is unique), then hold, then bind
        if drop_cloud:
            db.execute("delete from photos where hash = any(%s)", (sorted(drop_cloud),))
        if let_go:
            db.execute("update photos set drive_id = null, updated_at = now() where hash = any(%s)",
                       (sorted(let_go),))
        with db.cursor() as cur:
            if new_held:
                cur.executemany(
                    "insert into held (drive_id, rel_path, reason) values (%s, %s, %s) "
                    "on conflict (drive_id) do update set reason = excluded.reason, at = now()",
                    [(fid, rel, why) for fid, (rel, why) in new_held.items()])
            if binds:
                cur.executemany("update photos set drive_id = %s, updated_at = now() where hash = %s",
                                [(f["id"], h) for h, f in binds.items()])
        self.c["bound"] += len(binds)

        # a box is drawn only on a picture the shape Drive shows
        if binds:
            dims = {h: upright(f) for h, f in binds.items()}
            turned = []
            for key, h, mw, mh in db.execute(
                    "select key, hash, measured_w, measured_h from faces where hash = any(%s) "
                    "and bbox is not null and share is not null and measured_w > 0 and measured_h > 0",
                    (list(binds),)).fetchall():
                d = dims.get(h)
                if d and not same_shape((mw, mh), d):
                    turned.append((key,))
            if turned:
                with db.cursor() as cur:
                    cur.executemany("update faces set share = null where key = %s", turned)
            self.c["faces_turned"] += len(turned)
        # a library box on a video is on a frame Drive does not show: never drawn
        # (self-healing: corrects any row imported before this rule existed)
        r = db.execute("update faces f set share = null from photos p where p.hash = f.hash "
                       "and p.source = 'seed' and p.media = 'video' and f.frame is null and f.share is not null")
        self.c["video_boxes_cleared"] += r.rowcount if r.rowcount and r.rowcount > 0 else 0
        db.commit()
        if binds or self.c["held_library"] or self.c["unbound"]:
            say("library bound", bound=len(binds), unbound=self.c["unbound"], held=self.c["held_library"],
                duplicates=self.c["duplicates"], replaced=self.c["replaced"], faces_turned=self.c["faces_turned"])

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
                    self.errors[err_name(e)] += 1
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
        frows, crows, hrows = [], [], []
        for i, fc in enumerate(faces):
            cid = self.assign(fc["emb"], fc["det"], start=not f.get("personal"))
            if cid is None:
                continue
            frows.append(("{}::{}".format(h, i), h, cid, cid, [round(x, 5) for x in fc["bbox"]], n_here == 1,
                          fc["det"], round(fc["share"], 4), vec(fc["emb"])))
            crows.append((cid, cid))
            hrows.append((cid, cid, h))
        if frows:
            with self.db.cursor() as cur:            # a round trip per kind, not per face
                cur.executemany(
                    "insert into faces (key, hash, group_id, cluster_id, bbox, only_face, score, share, embedding) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector) on conflict (key) do nothing", frows)
                cur.executemany(
                    "insert into clusters (cluster_id, group_id, n) values (%s, %s, 0) on conflict do nothing", crows)
                cur.executemany(
                    "insert into cluster_hashes (cluster_id, group_id, hash) values (%s,%s,%s) "
                    "on conflict do nothing", hrows)
            self.c["faces"] += len(frows)
        self.db.commit()
        self.c["added"] += 1

    # -- the owner's Personal folder (migration 0010) ----------------------
    def nearest(self, emb):
        """The cluster a face belongs to, as assign() would place it, or None -
        without moving any centroid: looking is not joining."""
        import numpy as np
        k = len(self.cid)
        if not k:
            return None
        sims = self.C[:k] @ np.asarray(emb, dtype=np.float32)
        j = int(np.argmax(sims))
        return self.cid[j] if sims[j] >= JOIN else None

    def personal_scan(self, pfiles):
        """Each Personal file is looked at once: Drive's own rendering, the
        faces clearly in it, and the cluster each belongs to. Nothing is
        classified and nothing is spent here; whether it comes in is decided
        in the database (personal_verdicts), from the names as they are then."""
        if self.personal_per_run <= 0 or self.faces is None or not pfiles:
            return
        db = self.db
        seen = dict(db.execute("select drive_id, status from personal_seen").fetchall())
        tries = dict(db.execute("select drive_id, tries from personal_seen where status = 'error'").fetchall())
        todo = [f for f in sorted(pfiles, key=lambda f: f["rel"])
                if seen.get(f["id"]) is None or (seen[f["id"]] == "error" and tries.get(f["id"], 0) < VIDEO_TRIES)]
        self.c["personal_waiting"] = len(todo)
        todo = todo[:self.personal_per_run]
        if not todo:
            return
        import threading
        lock = threading.Lock()

        def look(f):
            try:
                jpeg = self.drive.image(f["id"], VIEW_PX)
                if not jpeg:
                    return f, None
                with lock:                                   # one detector, shared
                    found = self.faces.detect(jpeg)
                return f, [self.nearest(x["emb"]) or "" for x in found
                           if x["det"] >= START and x["share"] >= PERSONAL_SHARE]
            except Exception as e:                           # noqa: BLE001
                self.errors["personal_" + err_name(e)] += 1
                return f, None

        rows, done = [], 0

        def flush():
            if rows:
                with db.cursor() as cur:
                    cur.executemany(
                        "insert into personal_seen (drive_id, rel_path, subjects, status) values (%s,%s,%s,%s) "
                        "on conflict (drive_id) do update set subjects = excluded.subjects, status = excluded.status, "
                        "rel_path = excluded.rel_path, tries = personal_seen.tries + 1, at = now()", rows)
                db.commit()
                rows.clear()

        with cf.ThreadPoolExecutor(max_workers=self.workers) as pool:
            futs, it = set(), iter(todo)
            for f in it:                                    # a few in flight, never the whole list
                futs.add(pool.submit(look, f))
                if len(futs) >= self.workers * 2:
                    break
            while futs:
                fut = next(cf.as_completed(futs))
                futs.discard(fut)
                f, subjects = fut.result()
                rows.append((f["id"], f["rel"], subjects or [], "seen" if subjects is not None else "error"))
                self.c["personal_seen" if subjects is not None else "personal_error"] += 1
                done += 1
                if done % 200 == 0:
                    flush()
                if done % 1000 == 0:
                    say("personal", seen=done, of=len(todo))
                if self.deadline is not None and time.time() >= self.deadline:
                    self.c["personal_stopped"] = 1
                    continue                               # in flight finish; nothing new starts
                nxt = next(it, None)
                if nxt is not None:
                    futs.add(pool.submit(look, nxt))
        flush()

    def personal_wanted(self, pfiles):
        """The Personal files that qualify now and are not in the index yet:
        they go through process() like any new file - the library's three
        passes and the nudity rule - and start no new face cluster."""
        if not pfiles:
            return []
        ok = {d for (d,) in self.db.execute("select drive_id from personal_verdicts where qualifies").fetchall()}
        self.c["personal_qualify"] = len(ok)
        return [dict(f, personal=True) for f in pfiles if f["id"] in ok]

    # A Personal photograph shows only while it qualifies AS IT WAS STORED, not
    # only as it was first looked at: between the look and the store, a face's
    # nearest group can move (centroids learn as faces join), and on the first
    # live run 30 of 1,100 photos looked like a ticked person but were stored
    # as someone the app does not know. So: a ticked person must be among the
    # photo's people as the app shows them (photo_people - which also follows
    # the family's "not in it"), and with the switch on no face clearly in it,
    # as stored, may belong to anyone but a ticked person, the owner or his
    # partner. It runs after group(): store() files a new face under its own
    # cluster until grouping, so before it a ticked person in a grouped
    # cluster is not yet among the photo's people (411 hidden on run #15).
    SHOWN = """
        with ours as materialized (select hash, drive_id from photos where rel_path like %(prefix)s and drive_id is not null),
        pp as materialized (select x.hash, x.name from photo_people x where x.hash in (select hash from ours)),
        us as (select name from private_rules where kind = 'ignore'),
        stranger as (
          select distinct f.hash from faces f join ours o on o.hash = f.hash
          left join clusters c on c.cluster_id = f.cluster_id left join group_names g on g.group_id = c.group_id
          where f.share >= %(share)s and f.score >= %(det)s
            and (g.name is null or (g.name not in (select name from personal_people) and g.name not in (select name from us)))),
        good as (
          select o.hash from ours o join personal_verdicts v on v.drive_id = o.drive_id and v.qualifies
          where exists (select 1 from pp where pp.hash = o.hash and pp.name in (select name from personal_people))
            and (coalesce((select value from sync_state where key = 'personal_strict'), 'true') <> 'true'
                 or o.hash not in (select hash from stranger)))"""

    def personal_show(self):
        """A Personal photograph in the index shows exactly while it qualifies:
        a name unticked hides its photographs again, a name ticked or a face
        named shows them. Only ever un-hides what this rule hid."""
        db = self.db
        args = {"prefix": PERSONAL_PREFIX + "/%", "share": PERSONAL_SHARE, "det": START}
        hid = db.execute(self.SHOWN + """
            update photos p set hidden = true, hidden_by = 'rule:personal', hidden_at = now()
            where p.hash in (select hash from ours) and not p.hidden and p.hash not in (select hash from good)""",
                         args).rowcount
        back = db.execute(self.SHOWN + """
            update photos p set hidden = false, hidden_by = null, hidden_at = null
            where p.hidden_by like 'rule:personal%%' and p.hash in (select hash from good)""", args).rowcount
        db.commit()
        n = db.execute("select count(*) from photos where rel_path like %s and visible",
                       (PERSONAL_PREFIX + "/%",)).fetchone()[0]
        self.c["personal_shown"] = int(n)
        if n or hid or back:
            say("personal shown", shown=int(n), hidden_now=max(hid, 0), shown_again=max(back, 0))

    # -- video faces: a frame of their own -------------------------------
    def frames(self):
        """A face seen only in a video is shown on a frame of its own: pulled
        from the video on Drive at the library's timestamp, the same person
        found in it again by embedding (so the ring is on the right face), and
        judged by the library's sensitivity pass. Shown only if it passes;
        every attempt is recorded, so no frame is judged twice. One face per
        group per run - the group's best - for the groups the queue would ask
        if it had a face to show: flagged first, then the most photographed."""
        if self.frames_per_run <= 0 or self.faces is None or not hasattr(self.drive, "frame"):
            return
        import numpy as np
        db = self.db
        # materialized: inlined, the planner misjudged the candidates as one row
        # and re-ran the per-group count for each of ~18,000 (run #16 timed out)
        rows = db.execute("""
            with g as materialized (select group_id, name, answered, flagged from group_names),
            pc as materialized (
              select f.group_id, count(distinct f.hash) as photos,
                     bool_or(coalesce(f.share, 0) >= %s
                             and not (p.source = 'seed' and p.media = 'video' and f.frame is null)) as askable
              from faces f join photos p on p.hash = f.hash and p.visible
              where f.group_id is not null group by f.group_id),
            want as materialized (
              select pc.group_id, g.flagged, pc.photos from pc join g using (group_id)
              where not pc.askable
                and ((not g.answered and (g.flagged or pc.photos >= 2)) or g.name is not null))
            select distinct on (w.flagged, w.photos, w.group_id)
                   f.key, p.drive_id, f.embedding::text, w.group_id
            from want w
            join faces f on f.group_id = w.group_id
            join photos p on p.hash = f.hash and p.visible and p.media = 'video' and p.source = 'seed'
            left join frames fr on fr.key = f.key
            where f.frame is null and f.embedding is not null
              and split_part(f.key, ':', 2) ~ '_t[0-9]+$'
              and (fr.key is null or fr.status = 'error')
            order by w.flagged desc, w.photos desc, w.group_id, f.score desc nulls last, f.key""",
            (SUBJECT_SHARE,)).fetchall()
        todo = rows[:self.frames_per_run]
        self.c["frames_wanted"] = len(rows)
        if not todo:
            return
        import threading
        lock = threading.Lock()

        def look(row):
            try:
                return judge_frame(row)
            except Exception as e:                               # noqa: BLE001
                # recorded as an error and tried again next run - never lost
                self.errors["frame_" + err_name(e)] += 1
                return row[0], "error", {}, None, 0.0

        def judge_frame(row):
            key, fid, emb, _g = row
            ms = int(re.search(r"_t(\d+)$", key.split(":")[1]).group(1))
            jpeg = self.drive.frame(fid, ms)
            if not jpeg:
                return key, "error", None, None, 0.0
            from PIL import Image
            with Image.open(io.BytesIO(jpeg)) as im:
                w, h = im.size
            with lock:                                   # one detector, shared
                found = self.faces.detect(jpeg)
            want = parse_vec(emb)
            best = max(found, key=lambda fc: float(np.dot(fc["emb"], want)), default=None)
            if best is None or float(np.dot(best["emb"], want)) < FRAME_MATCH:
                return key, "noface", None, (w, h), 0.0
            try:
                v, usd = self.gemini.sensitivity(jpeg)
            except RuntimeError as e:
                if str(e).startswith("BLOCKED"):
                    return key, "held", {"blocked": "yes"}, (w, h), 0.0
                raise
            verdict = {k: str(v.get(k) or "")[:20] for k in ("nudity", "subject_age", "sexual")}
            if not frame_ok(v):
                return key, "held", verdict, (w, h), usd
            return key, "ok", verdict, (w, h, jpeg, best, len(found)), usd

        done, fr_rows, face_rows = 0, [], []

        def flush():
            with db.cursor() as cur:
                if fr_rows:
                    cur.executemany(
                        "insert into frames (key, status, jpeg, w, h, verdict) values (%s,%s,%s,%s,%s,%s::jsonb) "
                        "on conflict (key) do update set status = excluded.status, jpeg = excluded.jpeg, "
                        "w = excluded.w, h = excluded.h, verdict = excluded.verdict, at = now()", fr_rows)
                if face_rows:
                    cur.executemany(
                        "update faces set frame = %s, bbox = %s, share = %s, only_face = %s, "
                        "measured_w = %s, measured_h = %s where key = %s", face_rows)
            db.commit()
            fr_rows.clear()
            face_rows.clear()

        with cf.ThreadPoolExecutor(max_workers=self.workers) as pool:
            futs, it = {}, iter(todo)
            for row in it:
                futs[pool.submit(look, row)] = row
                if len(futs) >= self.workers * 2:
                    break
            while futs:
                fut = next(cf.as_completed(futs))
                futs.pop(fut)
                try:
                    key, status, verdict, extra, usd = fut.result()
                except Exception as e:                           # noqa: BLE001
                    self.errors["frame_" + type(e).__name__] += 1
                    key, status, verdict, extra, usd = None, None, None, None, 0.0
                self.spent += usd
                if key:
                    self.c["frames_" + status] += 1
                    if status == "ok":
                        w, h, jpeg, best, n = extra
                        fr_rows.append((key, "ok", jpeg, w, h, json.dumps(verdict)))
                        face_rows.append((key, [round(x, 5) for x in best["bbox"]], round(best["share"], 4),
                                          n == 1, w, h, key))
                    else:
                        wh = extra or (None, None)
                        fr_rows.append((key, status, None, wh[0], wh[1], json.dumps(verdict or {})))
                done += 1
                if done % 50 == 0:
                    flush()
                if done % 200 == 0:
                    say("frames", done=done, of=len(todo), shown=self.c["frames_ok"],
                        held=self.c["frames_held"], spent_usd=self.spent)
                if self.spent >= self.cap or (self.deadline is not None and time.time() >= self.deadline):
                    self.c["frames_stopped"] = 1
                    continue                               # in flight finish; nothing new starts
                nxt = next(it, None)
                if nxt is not None:
                    futs[pool.submit(look, nxt)] = nxt
        flush()
        say("frames", done=done, wanted=len(rows), shown=self.c["frames_ok"], held=self.c["frames_held"],
            noface=self.c["frames_noface"], failed=self.c["frames_error"])

    # -- videos ------------------------------------------------------------
    def videos(self):
        """A video plays only once all of it has been judged (migration 0009).
        Videos with a named person in them first, then the newest. A format no
        phone plays, or a file too big to judge, keeps its still and costs
        nothing. A video that fails is hidden everywhere; one not judged this
        time is tried again on a later run, VIDEO_TRIES times. Runs after
        private(), so nothing private is ever downloaded to be judged."""
        if self.videos_per_run <= 0 or not hasattr(self.drive, "meta") or not hasattr(self.gemini, "video"):
            return
        db = self.db
        rows = db.execute("""
            with named as materialized (select distinct hash from photo_people)
            select p.hash, p.drive_id, p.md5 from photos p
            left join video_checks v on v.hash = p.hash
            where p.visible and p.media = 'video' and p.drive_id is not null
              and (v.hash is null or (v.status = 'error' and v.tries < %s))
            order by (p.hash in (select hash from named)) desc, p.taken_at desc nulls last, p.hash""",
            (VIDEO_TRIES,)).fetchall()
        self.c["videos_wanted"] = len(rows)
        todo = rows[:self.videos_per_run]
        if not todo:
            return
        tmp = tempfile.mkdtemp(prefix="videos-")

        def judge(row):
            h, fid, md5 = row
            meta = self.drive.meta(fid)
            if meta.get("mime") in UNPLAYABLE_MIME:
                return "unplayable", "a format phones cannot play", None, None, None, 0.0
            if int(meta.get("size") or 0) > VIDEO_MAX_BYTES:
                return "unplayable", "too big to judge", None, None, None, 0.0
            n = hashlib.sha1(h.encode()).hexdigest()[:16]
            src, clip = os.path.join(tmp, n + ".src"), os.path.join(tmp, n + ".mp4")
            try:
                self.drive.download(fid, src, md5)
                p = probe(src)
                secs = int(round(p["seconds"])) if p["seconds"] else None
                mime = play_mime(p)
                if not mime:
                    return "unplayable", "a format phones cannot play", None, secs, None, 0.0
                remux(src, clip, p["codec"])
                verdicts, usd = self.gemini.video(clip, p["seconds"])
                status, why = video_verdict(verdicts)
                kept = [{k: v.get(k) for k in ("nudity", "subject_age", "sexual", "_blocked") if k in v}
                        for v in verdicts]                  # category words only, never the model's note
                return status, why or None, mime, secs, kept, usd
            finally:
                for x in (src, clip):
                    if os.path.exists(x):
                        os.unlink(x)

        def look(row):
            try:
                return row, judge(row)
            except Exception as e:                               # noqa: BLE001
                self.errors["video_" + err_name(e)] += 1         # recorded, tried again next run
                return row, ("error", err_name(e), None, None, None, 0.0)

        done = 0
        with cf.ThreadPoolExecutor(max_workers=max(1, min(self.workers, 3))) as pool:   # whole files on disk: few at once
            futs, it = set(), iter(todo)
            for row in it:
                futs.add(pool.submit(look, row))
                if len(futs) >= 3:
                    break
            while futs:
                fut = next(cf.as_completed(futs))
                futs.discard(fut)
                (h, _, _), (status, why, mime, secs, verdict, usd) = fut.result()
                self.spent += usd
                self.c["videos_" + status] += 1
                db.execute(
                    "insert into video_checks (hash, status, reason, mime, seconds, verdict, usd) "
                    "values (%s, %s, %s, %s, %s, %s::jsonb, %s) on conflict (hash) do update set "
                    "status = excluded.status, reason = excluded.reason, mime = excluded.mime, "
                    "seconds = excluded.seconds, verdict = excluded.verdict, usd = excluded.usd, "
                    "tries = video_checks.tries + 1, at = now()",
                    (h, status, why, mime, secs, json.dumps(verdict) if verdict is not None else None, round(usd, 5)))
                if status == "held":
                    db.execute("update photos set hidden = true, hidden_by = 'rule:video-check', hidden_at = now() "
                               "where hash = %s and not hidden", (h,))
                db.commit()
                done += 1
                if done % 25 == 0:
                    say("videos", done=done, of=len(todo), playable=self.c["videos_ok"],
                        held=self.c["videos_held"], spent_usd=self.spent)
                if self.spent >= self.cap or (self.deadline is not None and time.time() >= self.deadline):
                    self.c["videos_stopped"] = 1
                    continue                               # in flight finish; nothing new starts
                nxt = next(it, None)
                if nxt is not None:
                    futs.add(pool.submit(look, nxt))
        shutil.rmtree(tmp, ignore_errors=True)
        say("videos", done=done, wanted=len(rows), playable=self.c["videos_ok"], held=self.c["videos_held"],
            unplayable=self.c["videos_unplayable"], failed=self.c["videos_error"], spent_usd=self.spent)

    # -- people ------------------------------------------------------------
    def group(self):
        """Clusters -> people. The library's groups were decided by people
        (CLUSTER-MERGES.csv) and are pinned: never merged with one another.
        Every other cluster joins the nearest group whose running centroid
        meets it at 0.68 (chain_rounds' merge), never joining two different
        names (merge_clusters.py's rule)."""
        import numpy as np
        rows = self.db.execute(
            "select c.cluster_id, c.centroid::text, c.n, c.pinned, c.group_id, cn.name from clusters c "
            "left join cluster_names cn on cn.cluster_id = c.cluster_id "
            "where c.centroid is not null order by c.n desc, c.cluster_id").fetchall()
        pinned = [r for r in rows if r[3]]
        loose = [r for r in rows if not r[3]]
        gidx, gid, gnames = {}, [], []
        cap = len({r[4] for r in pinned}) + len(loose) + 1
        G = np.zeros((cap, 512), np.float32)          # running sums, one row per group
        for cid, cen, n, _, g, name in pinned:
            j = gidx.get(g)
            if j is None:
                j = gidx[g] = len(gid)
                gid.append(g)
                gnames.append(set())
            G[j] += parse_vec(cen) * max(int(n or 1), 1)
            if name:
                gnames[j].add(name)
        k = len(gid)
        Gn = G / np.maximum(np.linalg.norm(G, axis=1, keepdims=True), 1e-9)
        of = {}
        for cid, cen, n, _, _, name in loose:
            v = parse_vec(cen) * max(int(n or 1), 1)
            u = v / (float(np.linalg.norm(v)) or 1.0)
            placed = False
            if k:
                sims = Gn[:k] @ u
                top = np.argpartition(-sims, min(5, k) - 1)[:5]
                for j in top[np.argsort(-sims[top])]:
                    if sims[j] < MERGE:
                        break
                    if name and gnames[j] and name not in gnames[j]:
                        continue                  # two people with two names stay two
                    G[j] += v
                    Gn[j] = G[j] / (float(np.linalg.norm(G[j])) or 1.0)
                    if name:
                        gnames[j].add(name)
                    of[cid] = gid[j]
                    placed = True
                    break
            if not placed:
                G[k], Gn[k] = v, u
                gid.append(cid)
                gnames.append({name} if name else set())
                of[cid] = cid
                k += 1
        with self.db.cursor() as cur:
            cur.executemany("update clusters set group_id = %s where cluster_id = %s and group_id <> %s",
                            [(g, cid, g) for cid, g in of.items()])
            moved = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        self.db.execute("update cluster_hashes ch set group_id = c.group_id from clusters c "
                        "where c.cluster_id = ch.cluster_id and ch.group_id <> c.group_id")
        self.db.execute("update faces f set group_id = c.group_id from clusters c "
                        "where c.cluster_id = f.cluster_id and f.group_id is distinct from c.group_id")
        self.db.commit()
        self.c["clusters"] = len(rows)
        self.c["groups"] = k
        self.c["regrouped"] = moved

    def rebuild(self):
        """Queue, suggestions and people: derived, so rebuilt whole."""
        import numpy as np
        db = self.db
        names = dict(db.execute("select group_id, name from group_names where name is not null").fetchall())
        answered = {r[0] for r in db.execute("select group_id from group_names where answered").fetchall()}
        # "needs identifying": the library said ask someone else - asked first;
        # so is a CONTESTED face (people gave different answers, level): the
        # next person who has not answered it breaks the tie
        flagged = {r[0] for r in db.execute("select group_id from group_names where flagged").fetchall()}
        contested = {r[0] for r in db.execute("select group_id from group_names where contested").fetchall()}
        faces = collections.defaultdict(list)
        for key, h, g, score, share, only in db.execute(
                "select f.key, f.hash, f.group_id, f.score, coalesce(f.share, 0), f.only_face "
                "from faces f join photos p on p.hash = f.hash and p.visible "
                "where f.group_id is not null "
                "and not (p.source = 'seed' and p.media = 'video' and f.frame is null)").fetchall():
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
        first = flagged | contested
        for g, fs in sorted(faces.items(), key=lambda kv: (kv[0] not in first, -photos[kv[0]])):
            # settled faces leave; a contested one has a name in the lead but stays
            if g in answered or (photos[g] < 2 and g not in first):
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

        # everyone named on a photograph anyone can see: by a face, or by the
        # library's own record of who is in it
        counts = dict(db.execute(
            "select pp.name, count(distinct pp.hash)::int from photo_people pp "
            "join photos p on p.hash = pp.hash and p.visible group by pp.name").fetchall())
        people = [(name, cover_of[name][0] if name in cover_of else None, counts[name])
                  for name in sorted(set(names.values()) | set(counts)) if counts.get(name)]

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
    ap.add_argument("--frames", type=int, default=int(os.environ.get("FRAMES_PER_RUN", "1500")),
                    help="most video faces given a judged frame of their own this run")
    ap.add_argument("--videos", type=int, default=int(os.environ.get("VIDEOS_PER_RUN", "0")),
                    help="most videos watched whole this run, so they can play (a spend: 0 unless asked)")
    ap.add_argument("--personal", type=int, default=int(os.environ.get("PERSONAL_PER_RUN", "0")),
                    help="most Personal files looked at for the owner's chosen people this run (no spend)")
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
               budget=a.budget, cap_usd=a.cap_usd, workers=a.workers, max_minutes=a.max_minutes,
               frames=a.frames, videos=a.videos, personal=a.personal)
    w.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
