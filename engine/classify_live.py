r"""Classify the library with Gemini 3.1 Flash-Lite, live, concurrently.

    python classify_live.py --thumbs D:\_thumbs --store D:\_enrichment --dry-run
    python classify_live.py --thumbs D:\_thumbs --store D:\_enrichment --apply

WHY THIS EXISTS ALONGSIDE batch_classify.py

batch_classify.py speaks the Anthropic Batches API and only that: the endpoint,
the model id and the auth header are all Anthropic. The bake-off then chose a
different model - Gemini 3.1 Flash-Lite, at 87.8% against a reference no model
wrote, against Haiku's 74.5%, for less than half the price.

Gemini's batch API is a different protocol, not a different URL: JSONL uploaded
as a file, an operation to poll, results fetched separately. That is a second
asynchronous protocol to get right for a saving of about $20, on a job that
needs no answer within the hour but does need to be correct. Krish chose live on
2026-09-11. This runs the model the measurement picked, through the adapter the
measurement already proved.

WHY CONCURRENT

Live calls are network-bound and the account is not the constraint - the
bake-off measured ~1.6 s per call, so 61,679 files single-threaded is 27 hours.
Threads are the whole difference between a pass that runs overnight and one
that runs over a weekend.

WHAT IT COSTS, AND THE BRAKE

Measured in the bake-off at $0.453 per 1,000 images. A video contributes up to
four frames in ONE request, so requests are fewer than images and the bill
tracks images. --max-usd stops the run when the MEASURED spend reaches a
ceiling, rather than when an estimate says it should have.

RESUMABILITY

A hash already carrying a `kind` tag from this model is skipped. Kill it and
re-run; nothing already paid for is paid for twice.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from store import Store, TAGS                                    # noqa: E402
from batch_classify import PROMPT, assets_for                    # noqa: E402

MODEL = "gemini-3.1-flash-lite"
URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
       + MODEL + ":generateContent")
IN_PER_M, OUT_PER_M = 0.25, 1.50          # standard price, $/1M tokens
SOURCE = "google/" + MODEL

# Every category at the most permissive value the API allows. This is a
# classification pass over the user's OWN family photographs, and a filter that
# refuses to answer "is there nudity here" fails on precisely the images the
# question exists to find.
CATS = ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
MAX_FRAMES = 4
FIELDS = ("kind", "people", "subject", "keep", "sensitivity",
          "setting", "place", "era")


def call(paths, key, timeout=120):
    parts = []
    for p in paths[:MAX_FRAMES]:
        with open(p, "rb") as f:
            parts.append({"inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(f.read()).decode()}})
    parts.append({"text": PROMPT})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": 800},
            "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"}
                               for c in CATS]}
    r = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-goog-api-key": key},
        method="POST")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            d = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode(errors="replace")[:300]
        except Exception:                                        # noqa: BLE001
            pass
        raise RuntimeError("HTTP " + str(e.code) + ": " + detail) from e
    fb = (d.get("promptFeedback") or {}).get("blockReason")
    if fb:
        raise RuntimeError("BLOCKED: " + str(fb))
    txt = ""
    for c in d.get("candidates") or []:
        for part in ((c.get("content") or {}).get("parts") or []):
            txt += part.get("text", "")
    u = d.get("usageMetadata") or {}
    return txt, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def parse(txt):
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e <= s:
        return {}
    try:
        return json.loads(txt[s:e + 1])
    except json.JSONDecodeError:
        return {}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thumbs", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-usd", type=float, default=60.0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("GOOGLE_API_KEY is not set")

    st = Store(a.store)
    done = set()
    for r in st._read(TAGS):
        if r.get("tag") == "kind" and r.get("source") == SOURCE:
            done.add(r["hash"])
    assets = assets_for(a.thumbs)
    todo = sorted(h for h in assets if h not in done)
    if a.limit:
        todo = todo[:a.limit]

    frames = sum(min(len(assets[h]), MAX_FRAMES) for h in todo)
    print("model      : " + MODEL + " (live)")
    print("thumbs     : {:,} files have assets".format(len(assets)))
    print("already done by this model: {:,}".format(len(done)))
    print("to classify: {:,} files, {:,} images".format(len(todo), frames))
    print("estimate   : ${:.2f} at the measured rate".format(
        frames * 0.453 / 1000))
    print("ceiling    : ${:.2f}".format(a.max_usd))
    if not a.apply or a.dry_run:
        print("")
        print("dry run - nothing sent. Re-run with --apply.")
        return

    q = queue.Queue()
    for h in todo:
        q.put(h)
    lock = threading.Lock()
    stats = {"ok": 0, "fail": 0, "blocked": 0, "tin": 0, "tout": 0}
    stop = threading.Event()
    t0 = time.time()

    def cost():
        return ((stats["tin"] / 1e6) * IN_PER_M
                + (stats["tout"] / 1e6) * OUT_PER_M)

    def worker():
        while not stop.is_set():
            try:
                h = q.get_nowait()
            except queue.Empty:
                return
            txt = None
            for attempt in range(4):
                try:
                    txt, ti, to = call(assets[h], key)
                    with lock:
                        stats["tin"] += ti
                        stats["tout"] += to
                    break
                except RuntimeError as e:
                    m = str(e)
                    if "BLOCKED" in m:
                        with lock:
                            stats["blocked"] += 1
                        txt = None
                        break
                    # 429 and 503 are the account catching its breath, not a
                    # failure. Back off rather than spending the retry budget.
                    if attempt < 3 and ("429" in m or "503" in m
                                        or "500" in m):
                        time.sleep(2 ** attempt * 2)
                        continue
                    with lock:
                        stats["fail"] += 1
                    txt = None
                    break
                except Exception:                                # noqa: BLE001
                    with lock:
                        stats["fail"] += 1
                    txt = None
                    break
            if not txt:
                continue
            d = parse(txt)
            if not d:
                with lock:
                    stats["fail"] += 1
                continue
            try:
                conf = float(d.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            # The store is CSV append; two threads writing at once interleave
            # rows. Serialise the write, not the call.
            with lock:
                for f in FIELDS:
                    if f in d and d[f] != "":
                        st.tag(h, f, str(d[f]), SOURCE, conf)
                stats["ok"] += 1
                n = stats["ok"] + stats["fail"] + stats["blocked"]
                if n % 250 == 0:
                    el = time.time() - t0
                    rate = n / max(el, 1)
                    left = (len(todo) - n) / max(rate, 0.01) / 60
                    print("  {:,}/{:,}  ok={:,} fail={} blocked={}  "
                          "${:.2f}  {:.1f}/s  ~{:.0f} min left".format(
                              n, len(todo), stats["ok"], stats["fail"],
                              stats["blocked"], cost(), rate, left),
                          flush=True)
                if cost() >= a.max_usd:
                    print("")
                    print("CEILING REACHED at ${:.2f}. Stopping. Re-run to "
                          "continue; nothing is resubmitted.".format(cost()))
                    stop.set()

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(a.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("")
    print("finished in {:.0f} min".format((time.time() - t0) / 60))
    print("  classified {:,}".format(stats["ok"]))
    print("  failed     {:,}".format(stats["fail"]))
    print("  blocked    {:,}".format(stats["blocked"]))
    print("  tokens     {:,} in, {:,} out".format(stats["tin"], stats["tout"]))
    print("  MEASURED   ${:.2f}".format(cost()))


if __name__ == "__main__":
    main()
