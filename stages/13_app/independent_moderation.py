r"""Independent sexual-content audit for archives.krishraja.com.

The publishing gate in cloud_enrich.py remains the authority. This is a second,
independently trained detector over what the site can actually expose:

  * the 1600 px still for every visible photograph and video;
  * one frame per second, plus scene-change frames, for every visible video the
    site is allowed to play.

Every sample is committed separately. A killed run resumes without treating
unfinished work as clear. Any sexual positive hides the whole item immediately;
an error remains an error and never contributes to the cleared count. Hidden or
otherwise held material is never sent to this provider.

A video with no still anywhere is judged on what the site can show: a playable
one on every frame (and re-checked each run for a still), an unplayable one
withheld, since nothing of it can be checked.

The public Actions log contains counts only. Never add a path, Drive id, model
note, API response body, or content description to it.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, "stagepath.py")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401
import cloud_enrich as CE  # noqa: E402


MODEL = "omni-moderation-2024-09-26"  # pinned: a moving score cannot be calibrated
VIEW_PX = 1600                         # the largest photograph the site serves
SCENE_THRESHOLD = 0.30
# A JPEG is full-range: ffmpeg 6 converted a phone video's limited-range frames
# on its own, ffmpeg 8 refuses them ("Non full-range YUV is non-standard"), so
# the conversion is asked for. Identical output on ffmpeg 6.
JPEG_RANGE = ":out_range=full,format=yuvj420p"
MAX_IMAGE_BYTES = 20 * 1024 * 1024    # the provider's documented image limit
RETRYABLE = {429, 500, 502, 503, 504}
FRAMES_ONLY = "frames only"            # cleared on every frame: no still exists to check
UNVERIFIABLE = "unverifiable"          # withheld: nothing of it can be checked


# This pass's own failure words, and the Drive download's. Each is a literal in
# this code, so none can carry a path, id, response body or content description;
# naming them is what turns a repeated "RuntimeError" into something fixable.
OWN_ERRORS = {
    "image size": "image_size",
    "malformed response": "malformed_response",
    "retry exhausted": "retry_exhausted",
    "ffmpeg failed": "ffmpeg_failed",
    "frame extraction": "frame_extraction",
    "no frames": "no_frames",
    "scene extraction": "scene_extraction",
    "scene accounting": "scene_accounting",
    "download does not match Drive's md5": "md5_mismatch",
}


def error_kind(exc: Exception) -> str:
    """A fixed, non-sensitive error name safe for the public workflow log."""
    m = re.match(r"HTTP (\d{3})\b", str(exc))
    if m:
        return "http_" + m.group(1)
    if isinstance(exc, RuntimeError) and str(exc) in OWN_ERRORS:
        return OWN_ERRORS[str(exc)]
    return type(exc).__name__


class OpenAIModerator:
    """One image -> the provider's sexual flag and score.

    Only the provider's category flag is a hold. Scores are retained as audit
    evidence, not used as a custom threshold: the provider explicitly warns
    that scores can move between model versions.
    """

    API = "https://api.openai.com/v1/moderations"

    def __init__(self, key: str, http=None, backoff: float = 2.0):
        import requests
        self.key = key
        self.http = http or requests.Session()
        self.backoff = backoff
        self.local = threading.local()

    def moderate(self, jpeg: bytes) -> dict:
        if not jpeg or len(jpeg) > MAX_IMAGE_BYTES:
            raise RuntimeError("image size")
        data = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        payload = {"model": MODEL, "input": [{"type": "image_url", "image_url": {"url": data}}]}
        delay = self.backoff
        for attempt in range(6):
            try:
                r = self.http.post(
                    self.API,
                    headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=120,
                )
            except Exception as exc:  # requests' exception text can contain the request URL
                if attempt == 5:
                    raise RuntimeError(type(exc).__name__) from None
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            if r.status_code in RETRYABLE and attempt < 5:
                wait = r.headers.get("retry-after") if getattr(r, "headers", None) else None
                try:
                    pause = max(delay, float(wait)) if wait else delay
                except (TypeError, ValueError):
                    pause = delay
                time.sleep(min(pause, 60.0))
                delay = min(delay * 2, 60.0)
                continue
            if r.status_code >= 400:
                raise RuntimeError("HTTP {}".format(r.status_code))
            try:
                body = r.json()
                result = body["results"][0]
                categories = result["categories"]
                scores = result["category_scores"]
                applied = result.get("category_applied_input_types") or {}
                sexual = categories["sexual"]
                score = float(scores["sexual"])
                kinds = applied.get("sexual") or ["image"]
            except (KeyError, IndexError, TypeError, ValueError):
                raise RuntimeError("malformed response") from None
            if not isinstance(sexual, bool) or "image" not in kinds or not 0 <= score <= 1:
                raise RuntimeError("malformed response")
            return {"sexual": sexual, "score": score, "model": str(body.get("model") or MODEL)}
        raise RuntimeError("retry exhausted")


def _run_ffmpeg(args: list[str], timeout: int = 3600):
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("ffmpeg failed") from None


def extract_video_samples(src: str, out_dir: str) -> list[tuple[str, str]]:
    """Decode a video's one-per-second and scene-change samples.

    The returned keys are stable enough to resume. Completion is based on the
    files ffmpeg actually decoded, not on container duration metadata. A video
    yielding no frame is an error, never an empty pass.
    """
    fixed = os.path.join(out_dir, "fps-%08d.jpg")
    vf = "fps=fps=1:round=up,scale='min({},iw)':-2{}".format(VIEW_PX, JPEG_RANGE)
    r = _run_ffmpeg(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
                     "-map", "0:v:0", "-an", "-vf", vf, "-q:v", "4", fixed])
    if r.returncode != 0:
        raise RuntimeError("frame extraction")
    fixed_files = sorted(os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.startswith("fps-"))

    scene = os.path.join(out_dir, "scene-%08d.jpg")
    # Keep frame zero so ffmpeg can initialise its image encoder even when a
    # clip has no scene change at all; it is removed below when fps:00000000
    # already covers it.
    svf = "select='eq(n,0)+gt(scene,{})',showinfo,scale='min({},iw)':-2{}".format(
        SCENE_THRESHOLD, VIEW_PX, JPEG_RANGE)
    r = _run_ffmpeg(["ffmpeg", "-nostdin", "-loglevel", "info", "-y", "-i", src,
                     "-map", "0:v:0", "-an", "-vf", svf, "-fps_mode", "vfr", "-q:v", "4", scene])
    if r.returncode != 0:
        raise RuntimeError("scene extraction")
    scene_files = sorted(os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.startswith("scene-"))
    times = [int(round(float(x) * 1000)) for x in re.findall(rb"pts_time:([0-9]+(?:\.[0-9]+)?)", r.stderr)]
    if len(scene_files) != len(times):
        raise RuntimeError("scene accounting")

    samples = [("fps:{:08d}".format(i), p) for i, p in enumerate(fixed_files)]
    seen = set()
    for ms, path in zip(times, scene_files):
        # showinfo can repeat a timestamp in unusual streams; one stable key per instant.
        # A clip whose only picture falls between two whole seconds decodes no
        # per-second frame at all; its frame zero is then a sample in its own right.
        if (ms > 0 or not fixed_files) and ms not in seen:
            samples.append(("scene:{:012d}".format(ms), path))
            seen.add(ms)
    if not samples:
        raise RuntimeError("no frames")
    return samples


class Auditor:
    def __init__(self, db, drive, moderator, item_limit=0, sample_limit=0, workers=8, max_minutes=None):
        self.db, self.drive, self.moderator = db, drive, moderator
        self.item_limit = max(0, int(item_limit))
        self.sample_limit = max(0, int(sample_limit))
        self.workers = max(1, int(workers))
        self.deadline = None if max_minutes is None else time.time() + 60 * float(max_minutes)
        self.samples_started = 0
        self.counts = {"items": 0, "samples": 0, "held": 0, "errors": 0, "withheld": 0}

    def time_up(self) -> bool:
        return self.deadline is not None and time.time() >= self.deadline

    def sample_room(self) -> bool:
        return not self.sample_limit or self.samples_started < self.sample_limit

    def targets(self):
        """Outstanding site exposure, selected in one database query.

        A per-row status lookup here is invisible in a tiny test database but
        costs one network round trip for every live item before the first image
        is checked. Keep the resume filter in Postgres.

        A video cleared on its frames alone is looked at again every run, so a
        still that appears later is checked rather than trusted.
        """
        return self.db.execute(
            "select p.hash, p.drive_id, p.md5, p.media, coalesce(v.status, ''), "
            "coalesce(i.status, ''), coalesce(i.reason, ''), coalesce(i.expected_samples, 0) "
            "from photos p left join video_checks v on v.hash = p.hash "
            "left join independent_moderation i on i.hash = p.hash and i.model = %s "
            "where p.visible and (i.status is null or i.status not in ('ok','held') "
            "or (i.status = 'ok' and i.reason = %s)) "
            "order by (p.media = 'photo') desc, p.taken_at desc nulls last, p.hash",
            (MODEL, FRAMES_ONLY),
        ).fetchall()

    def cached_still(self, fid: str) -> bool:
        """Whether the site keeps its own copy of this file's still.

        The site serves `cache/<size>/<drive id>.jpg` from its storage before it
        asks Drive (web/lib/media.ts photoBytes), so such a still can be shown
        while Drive renders none. This pass cannot read it, so its existence
        keeps the item open. Unable to tell counts as yes.
        """
        try:
            with self.db.transaction():
                if not self.db.execute("select to_regclass('storage.objects') is not null").fetchone()[0]:
                    return True
                return bool(self.db.execute(
                    "select exists (select 1 from storage.objects where bucket_id = 'media' "
                    "and split_part(name, '/', 1) = 'cache' and split_part(name, '/', 3) = %s)",
                    (fid + ".jpg",),
                ).fetchone()[0])
        except Exception:
            return True

    def existing(self, h: str) -> dict[str, str]:
        return dict(self.db.execute(
            "select sample_key, status from independent_moderation_samples where hash = %s and model = %s",
            (h, MODEL),
        ).fetchall())

    def record_sample(self, h: str, key: str, result=None, error=None) -> None:
        if error is not None:
            status, sexual, score, actual, reason = "error", None, None, None, error_kind(error)
            self.counts["errors"] += 1
        else:
            sexual = bool(result["sexual"])
            status = "held" if sexual else "ok"
            score, actual = float(result["score"]), result["model"]
            reason = "sexual" if sexual else None
            self.counts["held"] += int(sexual)
        self.db.execute(
            "insert into independent_moderation_samples "
            "(hash, model, sample_key, actual_model, status, sexual, sexual_score, reason) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s) on conflict (hash, model, sample_key) do update set "
            "actual_model = excluded.actual_model, status = excluded.status, sexual = excluded.sexual, "
            "sexual_score = excluded.sexual_score, reason = excluded.reason, "
            "tries = independent_moderation_samples.tries + 1, at = now()",
            (h, MODEL, key, actual, status, sexual, score, reason),
        )

    def moderate_samples(self, h: str, samples: list[tuple[str, bytes | str]]) -> None:
        done = self.existing(h)
        todo = [(key, value) for key, value in samples if done.get(key) not in ("ok", "held")]
        if self.sample_limit:
            todo = todo[:max(0, self.sample_limit - self.samples_started)]
        if not todo or self.time_up():
            return

        def look(item):
            key, value = item
            try:
                if isinstance(value, bytes):
                    jpeg = value
                else:
                    with open(value, "rb") as fh:
                        jpeg = fh.read()
                return key, self.moderator.moderate(jpeg), None
            except Exception as exc:  # content and response details must never reach stdout or the DB
                return key, None, exc

        with cf.ThreadPoolExecutor(max_workers=self.workers) as pool:
            pending, it = set(), iter(todo)
            while len(pending) < self.workers:
                item = next(it, None)
                if item is None:
                    break
                pending.add(pool.submit(look, item))
                self.samples_started += 1
            since_commit = 0
            while pending:
                fut = next(cf.as_completed(pending))
                pending.remove(fut)
                key, result, error = fut.result()
                self.record_sample(h, key, result, error)
                self.counts["samples"] += 1
                since_commit += 1
                if since_commit >= 20:
                    self.db.commit()
                    since_commit = 0
                if not self.time_up() and self.sample_room():
                    item = next(it, None)
                    if item is not None:
                        pending.add(pool.submit(look, item))
                        self.samples_started += 1
            self.db.commit()

    def finish(self, h: str, media: str, expected: int, fatal: str | None = None,
               cleared: str | None = None, withhold: bool = False) -> str:
        row = self.db.execute(
            "select count(*) filter (where status in ('ok','held')), "
            "count(*) filter (where status = 'held'), max(sexual_score), "
            "max(actual_model) filter (where actual_model is not null), "
            "count(*) filter (where status = 'error') "
            "from independent_moderation_samples where hash = %s and model = %s",
            (h, MODEL),
        ).fetchone()
        checked, held, score, actual, errors = int(row[0]), int(row[1]), row[2], row[3], int(row[4])
        if held:
            status, reason = "held", "sexual"
        elif withhold:
            status, reason = "held", UNVERIFIABLE
        elif fatal:
            status, reason = "error", fatal
        elif errors:
            status, reason = "error", "sample error"
        elif expected and checked == expected:
            status, reason = "ok", cleared
        else:
            status, reason = "pending", None
        self.db.execute(
            "insert into independent_moderation "
            "(hash, model, actual_model, media, status, expected_samples, checked_samples, held_samples, "
            "max_sexual_score, reason) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "on conflict (hash, model) do update set actual_model = excluded.actual_model, "
            "media = excluded.media, status = excluded.status, expected_samples = excluded.expected_samples, "
            "checked_samples = excluded.checked_samples, held_samples = excluded.held_samples, "
            "max_sexual_score = excluded.max_sexual_score, reason = excluded.reason, "
            "tries = independent_moderation.tries + 1, at = now()",
            (h, MODEL, actual, media, status, expected, checked, held, score, reason),
        )
        if held:
            self.db.execute(
                "update photos set hidden = true, hidden_by = 'rule:independent-check', hidden_at = now() "
                "where hash = %s and not hidden", (h,),
            )
        elif withhold:
            self.db.execute(
                "update photos set hidden = true, hidden_by = 'rule:independent-unverifiable', hidden_at = now() "
                "where hash = %s and not hidden", (h,),
            )
        self.db.commit()
        return status

    def audit_item(self, row) -> None:
        h, fid, md5, media, video_status, prior, prior_reason, prior_expected = row
        samples = []
        playable = media == "video" and video_status == "ok"
        still = self.drive.image(fid, VIEW_PX)
        if prior == "ok" and prior_reason == FRAMES_ONLY:
            # Every frame is already clear; only a still that has since appeared
            # is new. Checked here, or kept open when only the site has it.
            if still:
                counted = int(self.existing(h).get("still") in ("ok", "held"))
                self.moderate_samples(h, [("still", still)])
                self.finish(h, media, prior_expected + 1 - counted)
            elif self.cached_still(fid):
                self.finish(h, media, prior_expected + 1, "no still")
                self.counts["errors"] += 1
            return
        if still:
            samples.append(("still", still))
        elif not playable:
            if media == "video" and prior == "error" and prior_reason == "no still":
                # No still on an earlier run either, and the site cannot play it:
                # nothing of it can be checked, so it is withheld until a person
                # releases it (Krish, 2026-10-15). One missing still is never
                # enough, because Drive's lookup also fails transiently.
                self.finish(h, media, 1, withhold=True)
                self.counts["withheld"] += 1
            else:
                self.finish(h, media, 1, "no still")
                self.counts["errors"] += 1
            return
        if not playable:
            self.moderate_samples(h, samples)
            self.finish(h, media, len(samples))
            return
        # A playable video still plays when Drive renders it no still, so its
        # frames are checked regardless.
        missing = 0 if still else 1

        with tempfile.TemporaryDirectory(prefix="independent-video-") as tmp:
            src = os.path.join(tmp, "source")
            frames = os.path.join(tmp, "frames")
            os.makedirs(frames)
            try:
                self.drive.download(fid, src, md5)
                samples.extend(extract_video_samples(src, frames))
            except Exception as exc:
                self.moderate_samples(h, samples)  # the visible still is still accounted for
                self.finish(h, media, max(1, len(samples) + missing), error_kind(exc))
                self.counts["errors"] += 1
                return
            self.moderate_samples(h, samples)
            if missing and not self.cached_still(fid):
                # Drive renders no still and the site keeps none, so its frames
                # are everything the site can show: all of them clear clears it
                # (Krish, 2026-10-15). A still checked on an earlier run counts.
                old = int(self.existing(h).get("still") in ("ok", "held"))
                self.finish(h, media, len(samples) + old, cleared=FRAMES_ONLY)
            elif missing:
                self.finish(h, media, len(samples) + missing, "no still")  # a still only the site has
                self.counts["errors"] += 1
            else:
                self.finish(h, media, len(samples))

    def audit_photos(self, rows) -> None:
        """Fetch and moderate independent stills concurrently, write serially.

        A photo is one sample, so sample-level concurrency inside audit_item()
        cannot help it. Network work fans out here while every checkpoint and
        hold is still committed by this thread through the single DB connection.
        """
        def look(row):
            h, fid, media = row[0], row[1], row[3]
            try:
                still = self.drive.image(fid, VIEW_PX)
                if not still:
                    return h, media, None, None, True
                return h, media, self.moderator.moderate(still), None, False
            except Exception as exc:
                return h, media, None, exc, False

        with cf.ThreadPoolExecutor(max_workers=self.workers) as pool:
            pending, it = set(), iter(rows)

            def fill() -> None:
                while len(pending) < self.workers and not self.time_up() and self.sample_room():
                    row = next(it, None)
                    if row is None:
                        break
                    pending.add(pool.submit(look, row))
                    self.samples_started += 1

            fill()
            while pending:
                fut = next(cf.as_completed(pending))
                pending.remove(fut)
                h, media, result, error, missing = fut.result()
                if missing:
                    self.finish(h, media, 1, "no still")
                    self.counts["errors"] += 1
                else:
                    self.record_sample(h, "still", result, error)
                    self.counts["samples"] += 1
                    self.finish(h, media, 1)
                self.counts["items"] += 1
                if self.counts["items"] % 25 == 0:
                    CE.say("independent progress", items=self.counts["items"], samples=self.counts["samples"],
                           held=self.counts["held"], errors=self.counts["errors"])
                fill()

    def coverage(self) -> dict:
        """Current site population, recomputed now rather than from the run's start."""
        row = self.db.execute(
            "with current as (select p.hash from photos p where p.visible), "
            "cleared as (select i.hash from independent_moderation i join current c using (hash) "
            "where i.model = %s and i.status = 'ok') "
            "select (select count(*) from current), (select count(*) from cleared), "
            "(select count(*) from independent_moderation i join photos p using (hash) "
            " where i.model = %s and i.status = 'held' and p.hidden_by = 'rule:independent-check'), "
            "(select count(*) from independent_moderation i join current c using (hash) "
            " where i.model = %s and i.status = 'error'), "
            "(select count(*) from independent_moderation i join current c using (hash) "
            " where i.model = %s and i.status = 'ok' and i.reason = %s), "
            "(select count(*) from independent_moderation i join photos p using (hash) "
            " where i.model = %s and i.status = 'held' and i.reason = %s "
            " and p.hidden_by = 'rule:independent-unverifiable')",
            (MODEL, MODEL, MODEL, MODEL, FRAMES_ONLY, MODEL, UNVERIFIABLE),
        ).fetchone()
        visible, cleared, held, errors, frames_only, withheld = map(int, row)
        return {"visible": visible, "cleared": cleared, "open": visible - cleared,
                "held_total": held, "error_items": errors,
                "frames_only": frames_only, "withheld_total": withheld}

    def run(self) -> dict:
        outstanding = self.targets()
        visible = int(self.db.execute("select count(*) from photos where visible").fetchone()[0])
        if self.item_limit:
            outstanding = outstanding[:self.item_limit]
        CE.say("independent start", visible=visible, outstanding=len(outstanding))
        photos = [row for row in outstanding if row[3] == "photo"]
        videos = [row for row in outstanding if row[3] != "photo"]
        self.audit_photos(photos)
        for row in videos:
            if self.time_up() or not self.sample_room():
                break
            self.audit_item(row)
            self.counts["items"] += 1
            if self.counts["items"] % 25 == 0:
                CE.say("independent progress", items=self.counts["items"], samples=self.counts["samples"],
                       held=self.counts["held"], errors=self.counts["errors"])
        report = self.coverage()
        receipt = dict(report, **self.counts)
        self.db.execute("insert into snapshots (kind, counts) values ('independent-moderation', %s::jsonb)",
                        (json.dumps(receipt),))
        self.db.commit()
        CE.say("independent done", **receipt)
        return receipt


def install(db) -> None:
    path = os.path.join(stagepath.ROOT, "web", "supabase", "migrations", "0015_independent_moderation.sql")
    with open(path, encoding="utf-8") as fh:
        db.execute(fh.read())
    db.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", type=int, default=int(os.environ.get("MODERATION_ITEMS_PER_RUN", "0")),
                    help="most archive items started this run; 0 means no item limit")
    ap.add_argument("--samples", type=int, default=int(os.environ.get("MODERATION_SAMPLES_PER_RUN", "0")),
                    help="most new API samples started this run; 0 means no sample limit")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("MODERATION_WORKERS", "8")))
    ap.add_argument("--max-minutes", type=float,
                    default=float(os.environ.get("MODERATION_MAX_MINUTES", "320")))
    ap.add_argument("--report", action="store_true", help="read current coverage without sending media")
    ap.add_argument("--require-complete", action="store_true", help="exit non-zero unless current visible coverage is complete")
    a = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("STOPPING: missing environment: DATABASE_URL")
        return 1
    if not a.report:
        missing = [k for k in ("GOOGLE_SERVICE_ACCOUNT_JSON", "OPENAI_API_KEY") if not os.environ.get(k)]
        if missing:
            print("STOPPING: missing environment: " + ", ".join(missing))
            return 1
    import psycopg
    try:
        db = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None)
        install(db)
        if a.report:
            report = Auditor(db, None, None).coverage()
            CE.say("independent report", **report)
        else:
            report = Auditor(db, CE.Drive(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
                             OpenAIModerator(os.environ["OPENAI_API_KEY"]),
                             item_limit=a.items, sample_limit=a.samples, workers=a.workers,
                             max_minutes=a.max_minutes).run()
        db.close()
    except Exception as exc:  # never put a connection string, path or API body in the public log
        CE.say("independent fatal", **{error_kind(exc).lower()[:32]: 1})
        return 1
    return 2 if a.require_complete and (report["open"] or report["error_items"]) else 0


if __name__ == "__main__":
    sys.exit(main())
