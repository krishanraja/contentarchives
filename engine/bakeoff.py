r"""Which model should classify 116,500 images? Measure it; do not argue about it.

WHY NOT JUST READ A LEADERBOARD

The Artificial Analysis feed prices every model and scores it on MMLU-Pro,
GPQA, AIME and LiveCodeBench. None of that measures whether a model can tell a
screenshot from a photograph, and the feed carries no vision benchmark and no
image-capability flag at all. Its cost column also cannot be trusted for this
job: it assumes one tokens-per-image figure, and every provider tokenises
images differently.

WHY THIS CORPUS CAN ANSWER IT

15,689 files here are already classified: 11,264 photo, 2,710 screenshot,
1,177 graphic, 244 document, 196 meme, 98 poster. That is a ground-truth set on
the actual data, free, already paid for. Sampling from it turns "which model is
better" into three measured numbers per candidate:

  agreement   does it reproduce the existing label for `kind`
  real cost   from the tokens the provider actually reports, not an assumption
  refusals    how often it declines or blanks - which matters most on the
              sensitivity question, where a refusal fails on exactly the files
              the flag exists to catch

SMOKE FIRST

Each provider's request shape is verified with ONE image before 300 are sent.
A wrong field name should cost a fraction of a cent and print the raw response,
not fail silently 300 times.

    python bakeoff.py --smoke
    python bakeoff.py --n 300
"""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from store import Store, TAGS                                    # noqa: E402
from batch_classify import PROMPT                                # noqa: E402

THUMBS = r"D:\_thumbs"
STORE = r"D:\_enrichment"
NLC = chr(10)
JOB_K = 116.5          # replaced by job_calls() at startup; see there

IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp",
           ".tif", ".tiff", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf",
           ".orf", ".rw2", ".pef", ".srw"}
VID_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".3g2", ".webm",
           ".wmv", ".mpg", ".mpeg", ".mpe", ".mod", ".tod", ".mts", ".m2ts",
           ".vob", ".flv", ".asf", ".mxf"}
# Forward slashes on purpose: os.walk takes them on Windows, and they keep the
# tree names out of reach of Python string escapes.
ROOTS = ["D:/ContentLibrary/Media/Personal", "D:/ContentLibrary/Media/Communal", "D:/ContentLibrary/Media/NoDate", "D:/ContentLibrary/Media/Pending-Segmentation"]

# name -> (provider, model id, $/1M in, $/1M out) at STANDARD price.
# Batch is half. Prices from the Artificial Analysis feed, 2026-09-09.
# gemini-2.5-flash-lite appears in the models list but 404s: "no longer
# available to new users". The list advertises models that cannot be called, so
# every id here was verified with a real request before being added.
CANDIDATES = {
    "gpt5-nano":     ("openai", "gpt-5-nano", 0.05, 0.40),
    "gemini31-lite": ("google", "gemini-3.1-flash-lite", 0.25, 1.50),
    "gemini35-lite": ("google", "gemini-3.5-flash-lite", 0.30, 2.50),
    "gpt5-mini":     ("openai", "gpt-5-mini", 0.25, 2.00),
    "haiku":         ("anthropic", "claude-haiku-4-5-20251001", 1.00, 5.00),
}


def post(url: str, headers: dict, body: dict, timeout: int = 120) -> dict:
    r = urllib.request.Request(url, data=json.dumps(body).encode(),
                               headers=headers, method="POST")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read())


# --- provider adapters ------------------------------------------------------
# Each returns (text, input_tokens, output_tokens). Raising is fine: the caller
# records it as a failure and keeps going.

def call_anthropic(model: str, jpeg: bytes, key: str) -> tuple[str, int, int]:
    d = post("https://api.anthropic.com/v1/messages",
             {"content-type": "application/json", "x-api-key": key,
              "anthropic-version": "2023-06-01"},
             {"model": model, "max_tokens": 400, "messages": [{"role": "user",
              "content": [
                  {"type": "image", "source": {"type": "base64",
                   "media_type": "image/jpeg",
                   "data": base64.b64encode(jpeg).decode()}},
                  {"type": "text", "text": PROMPT}]}]})
    u = d.get("usage", {})
    return ("".join(c.get("text", "") for c in d.get("content", [])),
            u.get("input_tokens", 0), u.get("output_tokens", 0))


def call_openai(model: str, jpeg: bytes, key: str) -> tuple[str, int, int]:
    b64 = base64.b64encode(jpeg).decode()
    # GPT-5 models are reasoning models, and max_completion_tokens covers
    # reasoning tokens too. At 800 the whole budget went to reasoning and the
    # answer came back EMPTY - while still billing 800 output tokens, which
    # made the "16x cheaper" model cost nearly what Haiku does for no output.
    # minimal effort plus a wider ceiling fixes both halves of that.
    body = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        "max_completion_tokens": 2000,
        "reasoning_effort": "minimal"}
    try:
        d = post("https://api.openai.com/v1/chat/completions",
                 {"content-type": "application/json",
                  "authorization": f"Bearer {key}"}, body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        # Older models want max_tokens and reject reasoning_effort; newer ones
        # are the reverse. Retry once with the other shape rather than making
        # the operator work out which family they picked.
        retried = False
        if "reasoning_effort" in detail:
            body.pop("reasoning_effort", None)
            retried = True
        if "max_completion_tokens" in detail or "max_tokens" in detail:
            body.pop("max_completion_tokens", None)
            body["max_tokens"] = 2000
            retried = True
        if not retried:
            raise RuntimeError(f"{e.code}: {detail[:400]}") from None
        d = post("https://api.openai.com/v1/chat/completions",
                 {"content-type": "application/json",
                  "authorization": f"Bearer {key}"}, body)
    u = d.get("usage", {})
    ch = (d.get("choices") or [{}])[0]
    return (ch.get("message", {}).get("content") or "",
            u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


def call_google(model: str, jpeg: bytes, key: str) -> tuple[str, int, int]:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    # Every category set to the most permissive value the API allows. This is a
    # classification task over the user's OWN family photographs, and a filter
    # that refuses to answer "is there nudity here" fails on precisely the
    # images the question exists to find.
    cats = ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
    d = post(url, {"content-type": "application/json", "x-goog-api-key": key},
             {"contents": [{"parts": [
                 {"inline_data": {"mime_type": "image/jpeg",
                                  "data": base64.b64encode(jpeg).decode()}},
                 {"text": PROMPT}]}],
              "generationConfig": {"maxOutputTokens": 800},
              "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"}
                                 for c in cats]})
    fb = d.get("promptFeedback", {}).get("blockReason")
    if fb:
        raise RuntimeError(f"BLOCKED: {fb}")
    cands = d.get("candidates") or []
    txt = ""
    if cands:
        if cands[0].get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT"):
            raise RuntimeError(f"BLOCKED: {cands[0].get('finishReason')}")
        txt = "".join(p.get("text", "")
                      for p in cands[0].get("content", {}).get("parts", []))
    u = d.get("usageMetadata", {})
    return (txt, u.get("promptTokenCount", 0),
            u.get("candidatesTokenCount", 0))


ADAPTERS = {"anthropic": call_anthropic, "openai": call_openai,
            "google": call_google}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
           "google": "GOOGLE_API_KEY"}


def parse(txt: str) -> dict:
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e <= s:
        return {}
    try:
        return json.loads(txt[s:e + 1])
    except json.JSONDecodeError:
        return {}


def sample(n: int) -> list[tuple[str, str, str]]:
    """(hash, thumb path, existing kind label) for files already classified."""
    st = Store(STORE)
    kinds = {}
    for row in st._read(TAGS):
        if row.get("tag") == "kind":
            kinds[row["hash"]] = row["value"]
    out = []
    for h, k in kinds.items():
        p = os.path.join(THUMBS, h[:2], h + ".jpg")
        if os.path.exists(p):
            out.append((h, p, k))
    random.seed(20260909)
    random.shuffle(out)
    # Stratify: an unstratified sample is ~72% photo and would barely test the
    # distinction that matters most, photo vs screenshot.
    by: dict[str, list] = collections.defaultdict(list)
    for r in out:
        by[r[2]].append(r)
    per = max(1, n // max(len(by), 1))
    picked: list = []
    for k, rows in by.items():
        picked += rows[:per]
    return picked[:n]


def job_calls() -> tuple[float, str]:
    """How many model calls the full pass actually costs, counted from disk.

    This was the literal 116.5 (thousand), written when the library was a
    different size and shape, and then multiplied into every headline cost in
    the comparison. It happened to stay close, which is worse than being wrong:
    a number nobody can trace is indistinguishable from one nobody checked.

    A video is not one call. frames.py samples 4 frames under 15 minutes and 5
    above, so videos dominate the bill far more than a file count suggests.
    """
    img = vid = 0
    for root in ROOTS:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                e = os.path.splitext(fn)[1].lower()
                if e in IMG_EXT:
                    img += 1
                elif e in VID_EXT:
                    vid += 1
    calls = img + vid * 4                      # 4 is the floor, 5 for long ones
    return calls / 1000.0, f"{img:,} images + {vid:,} videos x4 frames"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", help="comma-separated candidate names")
    a = ap.parse_args()

    names = a.only.split(",") if a.only else list(CANDIDATES)
    names = [n for n in names if n in CANDIDATES]

    have = {p: os.environ.get(KEY_ENV[p]) for p in set(
        CANDIDATES[n][0] for n in names)}
    for p, k in have.items():
        print(f"  {KEY_ENV[p]:<20} {'set' if k else 'MISSING - skipping'}")
    names = [n for n in names if have.get(CANDIDATES[n][0])]
    if not names:
        sys.exit("no keys available - set at least one of "
                 + ", ".join(KEY_ENV.values()))

    global JOB_K
    JOB_K, how = job_calls()
    print(NLC + f"full pass: {JOB_K*1000:,.0f} model calls  ({how})")

    rows = sample(2 if a.smoke else a.n)
    print(f"\nsample: {len(rows)} files, "
          f"{dict(collections.Counter(r[2] for r in rows))}")

    # A bake-off that prints an agreement percentage and keeps nothing is not
    # evidence. Agreement is measured against labels already in the store, so a
    # divergence may be the new model correcting the old one - and that can only
    # be judged by looking at the disagreements. The 2026-09-09 run cost real
    # money, was killed before its summary, and left nothing behind but a log
    # tail. So: every verdict is written as it happens, and the summary is
    # rewritten after each model rather than once at the end.
    vpath = os.path.join(STORE, "bakeoff-verdicts.csv")
    fresh = not os.path.exists(vpath)
    vf = open(vpath, "a", newline="", encoding="utf-8")
    vw = csv.writer(vf)
    if fresh:
        vw.writerow(["run", "model", "hash", "path", "stored_kind", "model_kind",
                     "agree", "people", "subject", "keep", "sensitivity",
                     "confidence"])
    run_id = time.strftime("%Y%m%dT%H%M%S")

    results = {}
    for name in names:
        provider, model, pin, pout = CANDIDATES[name]
        key = have[provider]
        agree = total = failed = blocked = 0
        tin = tout = 0
        sens: collections.Counter = collections.Counter()
        t0 = time.time()
        print(f"\n=== {name}  ({provider} / {model})")
        for i, (h, path, truth) in enumerate(rows, 1):
            try:
                with open(path, "rb") as f:
                    jpeg = f.read()
                txt, ti, to = ADAPTERS[provider](model, jpeg, key)
                tin += ti
                tout += to
            except Exception as e:                       # noqa: BLE001
                msg = str(e)
                if "BLOCK" in msg.upper() or "safety" in msg.lower():
                    blocked += 1
                else:
                    failed += 1
                if failed + blocked <= 2:
                    print(f"   ! {msg[:220]}")
                continue
            if a.smoke:
                print(f"   RAW: {txt[:300]}")
                print(f"   tokens in={ti} out={to}")
            d = parse(txt)
            if not d:
                failed += 1
                continue
            total += 1
            mk = str(d.get("kind", "")).strip().lower()
            hit = mk == truth.lower()
            if hit:
                agree += 1
            sens[str(d.get("sensitivity", "(absent)"))] += 1
            vw.writerow([run_id, name, h, path, truth, mk, int(hit),
                         d.get("people", ""), str(d.get("subject", ""))[:120],
                         d.get("keep", ""), d.get("sensitivity", ""),
                         d.get("confidence", "")])
            vf.flush()
            if i % 50 == 0:
                print(f"   {i}/{len(rows)} agree={agree}/{total}", flush=True)

        el = time.time() - t0
        n_ok = max(total, 1)
        cost_1k = ((tin / n_ok) * pin + (tout / n_ok) * pout) / 1000
        results[name] = {
            "agree": agree, "total": total, "failed": failed,
            "blocked": blocked, "tin_per": tin / n_ok, "tout_per": tout / n_ok,
            "cost_1k": cost_1k, "job": cost_1k * JOB_K, "sens": dict(sens),
            "s_per_file": el / max(len(rows), 1),
        }
        with open(os.path.join(STORE, "bakeoff.json"), "w",
                  encoding="utf-8") as jf:
            json.dump(results, jf, indent=1)      # after each model, not at end
        r = results[name]
        print(f"   agreement {agree}/{total} "
              f"({agree*100/n_ok:.1f}%)  failed {failed}  blocked {blocked}")
        print(f"   tokens/file {r['tin_per']:.0f} in {r['tout_per']:.0f} out")
        print(f"   MEASURED ${r['cost_1k']:.3f}/1,000  ->  full job "
              f"${r['job']:.2f} standard, ${r['job']/2:.2f} batched")
        print(f"   sensitivity spread: {r['sens']}")

    vf.close()
    if not a.smoke and results:
        print("\n" + "=" * 78)
        print(f"{'model':<20}{'agree':>8}{'fail':>6}{'block':>7}"
              f"{'$/1k':>9}{'JOB batched':>14}")
        print("-" * 78)
        for n, r in sorted(results.items(), key=lambda x: x[1]["job"]):
            pc = r["agree"] * 100 / max(r["total"], 1)
            print(f"{n:<20}{pc:>7.1f}%{r['failed']:>6}{r['blocked']:>7}"
                  f"{r['cost_1k']:>9.3f}{r['job']/2:>13.2f}")
        out = os.path.join(STORE, "bakeoff.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
        print(f"\n-> {out}")
        print(f"-> {vpath}  (every verdict, for eyeballing divergences)")
        print("\nAgreement is measured against Haiku's own earlier labels, so")
        print("Haiku will score near 100% by construction. Read it as 'how far")
        print("does this model diverge from the labels already in the store',")
        print("not as absolute accuracy. Divergences need eyeballing.")


if __name__ == "__main__":
    main()
