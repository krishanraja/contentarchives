r"""Classify the whole library through the Message Batches API, at half price.

WHY BATCH RATHER THAN LIVE

The live pass measured $0.75 per 1,000 files, identically across all six
shards. At ~84,000 files that is ~$87. The Batch API runs the same model on the
same prompt for 50% less, in exchange for asynchronous delivery - and nothing
here needs an answer within the hour. Most batches finish in under one anyway.

The constraint that shapes this file: a batch is capped at 100,000 requests OR
256 MB, whichever comes first. A base64 512px JPEG is ~40-70 KB, so SIZE binds
long before count - roughly 3,000 requests per batch, not 100,000. Chunking on
request count alone would build a 4 GB body and be rejected.

WHAT IT ASKS

One request per FILE, not per image: a video's sampled frames go into a single
message, so the model judges the clip rather than five unrelated stills.

Beyond the original kind/people/subject/keep, three fields the swipe game needs:

  sensitivity   two tiers, deliberately distinct. A 20-year family archive
                contains children in the bath and at the beach; those are not
                the same thing as adult intimate content, and filing them in
                one drawer is both wrong and unkind.
                  intimate       -> quarantined
                  private-family -> stays in the chronology, never surfaced in
                                    the swipe game or any shared view
                  none           -> ordinary
  place/setting where it was taken, from signage, architecture, landscape
  era           a visual decade guess, which is the only date signal available
                for the 5,433 files that have no date at all

RESUMABILITY

Batch ids are written to state.json as they are created. A run that dies is
re-entered by polling the ids already there; nothing already paid for is
resubmitted. Results are retained by the API for 29 days.

    python batch_classify.py --thumbs D:\_thumbs --store D:\_enrichment --submit
    python batch_classify.py --thumbs D:\_thumbs --store D:\_enrichment --collect
"""

from __future__ import annotations

import argparse
import base64
import collections
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from store import Store                                          # noqa: E402

API = "https://api.anthropic.com/v1/messages/batches"
MODEL = "claude-haiku-4-5-20251001"
VERSION = "2023-06-01"

# 256 MB is the hard limit; 200 MB leaves room for JSON overhead around the
# base64 payloads, which is not negligible at thousands of requests.
MAX_BATCH_BYTES = 200 * 1024 * 1024
MAX_BATCH_REQUESTS = 3000

PROMPT = """Classify this for a personal photo library. If several images are
shown they are frames from ONE video - judge the video as a whole.

Reply with ONLY a JSON object, no prose:
{"kind":"...","people":0,"subject":"...","keep":true,
 "sensitivity":"none","setting":"...","place":"","era":"unclear",
 "confidence":0.0}

kind, exactly one of:
  photo        a photograph someone took
  screenshot   a capture of a screen, app or webpage
  meme         a joke, forward, or graphic with overlaid text
  document     a scan, receipt, form, ticket, certificate
  graphic      a logo, icon, map tile, wallpaper, web asset
  poster       a flyer, invitation or advertisement

people      how many distinct human faces are visible (0 if none)
subject     at most 5 words describing what it shows
keep        true if this belongs in a personal photo library as a memory

sensitivity, exactly one of:
  none            ordinary content
  private-family  private but innocent: young children bathing, in nappies or
                  undressed; medical or injury images; anything a family would
                  keep but not show to visitors
  intimate        adult nudity or sexual content
  Judge what is actually visible. Ordinary swimwear at a beach or pool is
  "none". A child in a bath is "private-family", never "intimate".

setting     indoor, outdoor, or unclear
place       a specific place if you can identify one from signage, architecture,
            landscape or language - "Paris", "Sydney Opera House", "India".
            Empty string if you cannot. Do not guess.
era         visual decade from film grain, fashion, technology, print style:
            1990s, 2000s, 2010s, 2020s, or unclear

confidence  0.0-1.0

Judge the image itself. A photograph of a document is a document. A screenshot
of a photograph is a screenshot."""


def _req(url: str, key: str, data: bytes | None = None,
         method: str = "GET") -> dict:
    r = urllib.request.Request(url, data=data, method=method, headers={
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": VERSION,
    })
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read())


def assets_for(thumbs: str) -> dict[str, list[str]]:
    """hash -> the images to send for it.

    A video with sampled frames contributes <hash>_f0..fN; everything else
    contributes its single <hash>.jpg. Frames win where both exist, because
    five frames say more about a clip than its 10% thumbnail does.
    """
    by: dict[str, list[str]] = collections.defaultdict(list)
    single: dict[str, str] = {}
    for sub in sorted(os.listdir(thumbs)):
        d = os.path.join(thumbs, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".jpg"):
                continue
            stem = fn[:-4]
            if "_f" in stem:
                h, _, idx = stem.rpartition("_f")
                if idx.isdigit():
                    by[h].append(os.path.join(d, fn))
                    continue
            single[stem] = os.path.join(d, fn)
    out: dict[str, list[str]] = {}
    for h, paths in by.items():
        out[h] = sorted(paths)
    for h, p in single.items():
        out.setdefault(h, [p])
    return out


def build_request(h: str, paths: list[str]) -> tuple[dict, int] | None:
    content: list[dict] = []
    total = 0
    for p in paths[:5]:                      # the cap, enforced again here
        try:
            with open(p, "rb") as f:
                b = base64.b64encode(f.read()).decode()
        except OSError:
            continue
        total += len(b)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": b}})
    if not content:
        return None
    content.append({"type": "text", "text": PROMPT})
    return {
        "custom_id": h,                       # blake2b hex is 64 chars: valid
        "params": {"model": MODEL, "max_tokens": 400,
                   "messages": [{"role": "user", "content": content}]},
    }, total


def submit(a, key: str, st: Store, state: dict) -> None:
    done = st.known_hashes()
    assets = assets_for(a.thumbs)
    todo = {h: p for h, p in assets.items() if h not in done}
    print(f"assets: {len(assets):,}   already classified: {len(done):,}   "
          f"to do: {len(todo):,}")
    submitted = {h for b in state["batches"] for h in b["hashes"]}
    todo = {h: p for h, p in todo.items() if h not in submitted}
    print(f"already submitted in an earlier run: {len(submitted):,}   "
          f"remaining: {len(todo):,}")
    if a.limit:
        todo = dict(list(todo.items())[:a.limit])
        print(f"  limited to {len(todo):,}")
    if not todo:
        print("nothing to submit.")
        return

    reqs: list[dict] = []
    hashes: list[str] = []
    size = 0
    n_batches = 0

    def flush() -> None:
        nonlocal reqs, hashes, size, n_batches
        if not reqs:
            return
        body = json.dumps({"requests": reqs}).encode()
        print(f"  submitting {len(reqs):,} requests, "
              f"{len(body)/1024**2:.0f} MB ...", end="", flush=True)
        try:
            d = _req(API, key, body, "POST")
        except urllib.error.HTTPError as e:
            print(f" FAILED {e.code}: {e.read()[:300]!r}")
            sys.exit("stopping - nothing further submitted")
        state["batches"].append({"id": d["id"], "hashes": hashes,
                                 "submitted": time.time()})
        save_state(a.store, state)
        n_batches += 1
        print(f" {d['id']}")
        reqs, hashes, size = [], [], 0

    for h, paths in todo.items():
        built = build_request(h, paths)
        if not built:
            continue
        r, b = built
        if reqs and (size + b > MAX_BATCH_BYTES or
                     len(reqs) >= MAX_BATCH_REQUESTS):
            flush()
        reqs.append(r)
        hashes.append(h)
        size += b
    flush()
    print(f"\n{n_batches} batch(es) submitted. Run again with --collect.")


def collect(a, key: str, st: Store, state: dict) -> None:
    tin = tout = ok = bad = 0
    pending = 0
    for b in state["batches"]:
        if b.get("collected"):
            continue
        info = _req(f"{API}/{b['id']}", key)
        status = info.get("processing_status")
        if status != "ended":
            counts = info.get("request_counts", {})
            print(f"  {b['id']}: {status}  {counts}")
            pending += 1
            continue

        url = info.get("results_url")
        r = urllib.request.Request(url, headers={
            "x-api-key": key, "anthropic-version": VERSION})
        n = 0
        with urllib.request.urlopen(r, timeout=600) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                h = rec.get("custom_id", "")
                res = rec.get("result", {})
                if res.get("type") != "succeeded":
                    bad += 1
                    continue
                msg = res.get("message", {})
                u = msg.get("usage", {})
                tin += u.get("input_tokens", 0)
                tout += u.get("output_tokens", 0)
                txt = "".join(c.get("text", "")
                              for c in msg.get("content", []))
                s, e = txt.find("{"), txt.rfind("}")
                if s < 0 or e <= s:
                    bad += 1
                    continue
                try:
                    d = json.loads(txt[s:e + 1])
                except json.JSONDecodeError:
                    bad += 1
                    continue
                conf = float(d.get("confidence", 0) or 0)
                src = "model:haiku-batch"
                for k in ("kind", "subject", "sensitivity", "setting",
                          "place", "era"):
                    if d.get(k) not in (None, ""):
                        st.tag(h, k, str(d[k]), src, conf)
                if d.get("people") is not None:
                    st.tag(h, "people_count", str(d["people"]), src, conf)
                if d.get("keep") is not None:
                    st.tag(h, "keep", "yes" if d["keep"] else "no", src, conf)
                ok += 1
                n += 1
        b["collected"] = True
        save_state(a.store, state)
        print(f"  {b['id']}: collected {n:,}")

    spend = tin / 1e6 * a.rate_in + tout / 1e6 * a.rate_out
    print(f"\ncollected {ok:,}, failed {bad:,}, batches still running {pending}")
    if ok:
        print(f"  tokens {tin:,} in / {tout:,} out")
        print(f"  MEASURED COST this collection: ${spend:.2f} "
              f"(${spend/ok*1000:.2f} per 1,000)")


def state_path(store: str) -> str:
    return os.path.join(store, "batch-state.json")


def save_state(store: str, state: dict) -> None:
    p = state_path(store)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thumbs", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    # Batch pricing is half of standard. These are the defaults the live pass
    # was costed at, halved; pass explicit values to correct them.
    ap.add_argument("--rate-in", type=float, default=0.50)
    ap.add_argument("--rate-out", type=float, default=2.50)
    a = ap.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("set ANTHROPIC_API_KEY - this script never stores a key")

    os.makedirs(a.store, exist_ok=True)
    p = state_path(a.store)
    state = json.load(open(p, encoding="utf-8")) if os.path.exists(p) \
        else {"batches": []}
    st = Store(a.store)

    if a.submit:
        submit(a, key, st, state)
    if a.collect:
        collect(a, key, st, state)
    if not a.submit and not a.collect:
        n = sum(1 for b in state["batches"] if not b.get("collected"))
        print(f"{len(state['batches'])} batch(es) known, {n} not yet collected")


if __name__ == "__main__":
    main()
