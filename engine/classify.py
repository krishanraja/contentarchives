r"""Ask a vision model what each file actually is, cheaply and resumably.

WHY A CHEAP MODEL

The question is classification - screenshot, meme, document, or photograph;
roughly what is in it; are there people - not reasoning. Measured on this
corpus, metadata alone left 8,262 files genuinely undecidable: `042.jpg` (a
toddler in dinosaur pyjamas) and a forwarded Ganesh Utsav flyer are both JPEGs
of a couple of hundred KB with no camera EXIF, and no rule separates them. A
vision model separates them at a glance, and a small one does it as well as a
large one.

So this defaults to Haiku. Opus is worth paying for on face identity and on the
residue that comes back uncertain - not on 79,300 rounds of "is this a
screenshot".

WHY IT IS BUILT TO BE INTERRUPTED

The store records what has been classified, and this skips it. A run that dies
- watchdog, network, laptop lid - costs nothing already paid for. On a corpus
this size an all-or-nothing batch is a batch that never finishes.

COST IS PRINTED, NOT ESTIMATED

Every response's token usage is accumulated and reported per 1,000 files, so
the decision to continue is made on a measured number rather than my guess.

    python classify.py --thumbs D:\_thumbs --store D:\_PhotoAudit\enrichment
    python classify.py ... --limit 200        # a costed tranche
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from store import Store                                          # noqa: E402

API = "https://api.anthropic.com/v1/messages"
MODEL_CHEAP = "claude-haiku-4-5-20251001"
MODEL_STRONG = "claude-opus-5"

PROMPT = """Classify this image for a personal photo library.

Reply with ONLY a JSON object, no prose:
{"kind": "...", "people": 0, "subject": "...", "keep": true, "confidence": 0.0}

kind must be exactly one of:
  photo        - a photograph someone took
  screenshot   - a capture of a screen, app or webpage
  meme         - a joke, forward, or graphic with overlaid text
  document     - a scan, receipt, form, ticket, certificate
  graphic      - a logo, icon, map tile, wallpaper, web asset
  poster       - a flyer, invitation or advertisement

people  = how many human faces are visible (0 if none)
subject = at most 5 words describing what it shows
keep    = true if this belongs in a personal photo library as a memory
confidence = 0.0-1.0, how sure you are

Judge the image itself. A photograph of a document is a document. A screenshot
of a photograph is a screenshot."""


def call(api_key: str, model: str, jpeg: bytes) -> tuple[dict, int, int]:
    body = json.dumps({
        "model": model,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/jpeg",
                                         "data": base64.b64encode(jpeg).decode()}},
            {"type": "text", "text": PROMPT},
        ]}],
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read())
    txt = "".join(c.get("text", "") for c in d.get("content", []))
    u = d.get("usage", {})
    s, e = txt.find("{"), txt.rfind("}")
    parsed = json.loads(txt[s:e + 1]) if s >= 0 and e > s else {}
    return parsed, u.get("input_tokens", 0), u.get("output_tokens", 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thumbs", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--strong", action="store_true", help="use Opus, for the residue")
    ap.add_argument("--only", help="file listing hashes to do, one per line")
    a = ap.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("set ANTHROPIC_API_KEY - this script never stores a key")

    st = Store(a.store)
    done = st.known_hashes()
    print(f"already classified: {len(done):,}")

    wanted = None
    if a.only:
        wanted = {l.strip() for l in open(a.only, encoding="utf-8") if l.strip()}

    todo = []
    for sub in sorted(os.listdir(a.thumbs)):
        d = os.path.join(a.thumbs, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".jpg"):
                continue
            h = fn[:-4]
            if h in done or (wanted is not None and h not in wanted):
                continue
            todo.append((h, os.path.join(d, fn)))
    print(f"to classify: {len(todo):,}")
    if a.limit:
        todo = todo[:a.limit]
        print(f"  this tranche: {len(todo):,}")

    model = MODEL_STRONG if a.strong else MODEL_CHEAP
    tin = tout = ok = bad = 0
    t0 = time.time()
    for i, (h, p) in enumerate(todo, 1):
        try:
            with open(p, "rb") as f:
                jpeg = f.read()
            res, ti, to = call(key, model, jpeg)
            tin += ti
            tout += to
        except Exception as e:
            bad += 1
            if bad <= 5:
                print(f"  ! {h[:12]}: {e}")
            continue
        if not res:
            bad += 1
            continue
        conf = float(res.get("confidence", 0) or 0)
        src = f"model:{'opus' if a.strong else 'haiku'}"
        for k in ("kind", "subject"):
            if res.get(k):
                st.tag(h, k, str(res[k]), src, conf)
        if res.get("people") is not None:
            st.tag(h, "people_count", str(res["people"]), src, conf)
        if res.get("keep") is not None:
            st.tag(h, "keep", "yes" if res["keep"] else "no", src, conf)
        ok += 1
        if i % 25 == 0:
            el = time.time() - t0
            print(f"  {i:,}/{len(todo):,}  ok={ok} bad={bad}  "
                  f"{tin/max(i,1):.0f} in-tok/file  {el/max(i,1):.2f}s/file", flush=True)

    el = time.time() - t0
    print(f"\nclassified {ok:,}, failed {bad:,}, in {el/60:.1f} min")
    if ok:
        print(f"  tokens: {tin:,} in, {tout:,} out")
        print(f"  per 1,000 files: {tin/ok*1000:,.0f} in, {tout/ok*1000:,.0f} out")
        print("  multiply by the model's rate for the real cost of the full corpus.")


if __name__ == "__main__":
    main()
