r"""Embed every description, so the library can be asked in words rather than keywords.

    python embed_descriptions.py                 # report, send nothing
    python embed_descriptions.py --apply
    python embed_descriptions.py --ask "the afternoon everyone was squinting"

WHY THIS EXISTS

`library.db` already carries a full-text index over fifteen fields, and it
matches SPELLING. `search MATCH 'beach'` finds the word "beach" and cannot find
"we were all squinting into the sun", though a description saying exactly that
sits in the row. Krish, 2026-09-24: *"the objective should be to be able to
build a tool that allows me to 'talk' the content I want to the surface"*.

The descriptions are already written and already paid for - 85,368 of them at
99.9% coverage, averaging 277 characters. What is missing is a vector per file
and something to compare them with, and that is this.

THE VECTORS ARE NOT PAIRED BY POSITION WITH ANYTHING

Learning 45 is a positional cache that drifted until 11,347 of 11,611 vectors
described the wrong photograph while every row count agreed, and its durable
fix is "not to pair by position at all - put the payload in the row that
describes it". A numpy array cannot hold a hash in the row, so the compromise
is narrow and deliberate: each SHARD is one `.npz` holding its hashes and its
vectors, written ONCE and atomically by `os.replace`. Nothing is ever appended
to a vector file, so the two arrays in it cannot drift apart; a killed run
loses a shard and redoes it whole.

WHAT IT COSTS, AND THE BRAKE

gemini-embedding-001 at 768 dimensions, batched 100 at a time. 85,368
descriptions are about 5.6M tokens. `--max-usd` stops on the MEASURED spend,
not on an estimate, exactly as `classify_live.py` does.

RESUMABLE

A hash already in a shard is skipped. Kill it and re-run; nothing already paid
for is paid for twice.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P                                               # noqa: E402

MODEL = "gemini-embedding-001"
URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
       + MODEL + ":batchEmbedContents")
ONE = ("https://generativelanguage.googleapis.com/v1beta/models/"
       + MODEL + ":embedContent")
DIM = 768
PER_M = 0.15                       # $/1M input tokens, standard price
DB = os.path.join(P.AUDIT, "library.db")
OUT = os.path.join(P.AUDIT, "desc-vectors")


def shards(out):
    return sorted(glob.glob(os.path.join(out, "shard-*.npz")))


def done_hashes(out):
    import numpy as np
    have = set()
    for s in shards(out):
        try:
            with np.load(s, allow_pickle=False) as z:
                have.update(z["hash"].tolist())
        except Exception as e:                                   # noqa: BLE001
            print("  unreadable shard {}: {}".format(os.path.basename(s), e))
    return have


def embed(texts, key, dim=DIM, timeout=180):
    """-> list of vectors. Raises on anything it cannot parse."""
    reqs = [{"model": "models/" + MODEL,
             "content": {"parts": [{"text": t}]},
             "outputDimensionality": dim} for t in texts]
    r = urllib.request.Request(
        URL, data=json.dumps({"requests": reqs}).encode(),
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
        raise RuntimeError("HTTP {}: {}".format(e.code, detail)) from e
    embs = d.get("embeddings") or []
    if len(embs) != len(texts):
        raise RuntimeError("asked for {} embeddings, got {}".format(
            len(texts), len(embs)))
    out = []
    for e in embs:
        v = (e or {}).get("values") or []
        if len(v) != dim:
            raise RuntimeError("expected {} dims, got {}".format(dim, len(v)))
        out.append(v)
    return out


def ask(a):
    """Search by meaning. Prints what it could NOT see, every time."""
    import numpy as np
    files = shards(a.out)
    if not files:
        print("no vectors yet - run with --apply first")
        return 2
    H, V = [], []
    for s in files:
        with np.load(s, allow_pickle=False) as z:
            H.append(z["hash"]); V.append(z["vec"])
    H = np.concatenate(H); V = np.concatenate(V).astype(np.float32)
    V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("GOOGLE_API_KEY is not set")
        return 1
    q = np.array(embed([a.ask], key)[0], dtype=np.float32)
    q /= (np.linalg.norm(q) + 1e-9)
    sims = V @ q
    top = np.argsort(-sims)[:a.top]

    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")), uri=True)
    total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print('"{}"'.format(a.ask))
    print()
    for i in top:
        h = str(H[i])
        row = db.execute(
            "SELECT path, year FROM files WHERE hash=? LIMIT 1", (h,)).fetchone()
        desc = db.execute(
            "SELECT value FROM resolved WHERE hash=? AND field='description'",
            (h,)).fetchone()
        if not row:
            continue
        print("  {:.3f}  {}  {}".format(
            float(sims[i]), (row[1] or "????"), os.path.basename(row[0])[:46]))
        if desc:
            print("         {}".format(desc[0][:104]))
    # THE COVERAGE IS PART OF THE ANSWER, NOT A FOOTNOTE. A result that is
    # silently blind to a third of the library is this project's recurring
    # failure in a friendlier costume.
    print()
    print("  searched {:,} of {:,} files ({:.1f}%). The rest have no description "
          "and cannot match anything.".format(len(H), total, 100.0 * len(H) / total))
    db.close()
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--shard-size", type=int, default=5000)
    ap.add_argument("--max-usd", type=float, default=10.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ask", default="", help="search by meaning and exit")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()

    if a.ask:
        return ask(a)

    import numpy as np
    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")), uri=True)
    rows = db.execute(
        "SELECT r.hash, r.value FROM resolved r "
        "JOIN files f ON f.hash = r.hash "
        "WHERE r.field='description' AND r.value <> ''").fetchall()
    total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    db.close()
    # One vector per HASH. The same content under two paths is one photograph.
    seen, uniq = set(), []
    for h, v in rows:
        if h in seen:
            continue
        seen.add(h)
        uniq.append((h, v))
    print("descriptions : {:,} across {:,} files".format(len(uniq), total))

    os.makedirs(a.out, exist_ok=True)
    have = done_hashes(a.out)
    todo = [(h, v) for h, v in uniq if h not in have]
    print("already done : {:,}".format(len(have)))
    print("to embed     : {:,}".format(len(todo)))
    if a.limit:
        todo = todo[:a.limit]
    chars = sum(len(v) for _, v in todo)
    est = (chars / 4 / 1e6) * PER_M
    print("estimate     : ${:.2f} at {:.2f}/1M tokens".format(est, PER_M))
    print("ceiling      : ${:.2f}".format(a.max_usd))
    if not todo:
        print("\nnothing to do")
        return 0
    if not a.apply:
        print("\ndry run - nothing sent. Re-run with --apply.")
        return 0

    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("GOOGLE_API_KEY is not set")

    t0 = time.time()
    spent_chars = 0
    buf_h, buf_v = [], []
    n = fail = 0
    shard_i = len(shards(a.out))

    def flush_shard():
        nonlocal buf_h, buf_v, shard_i
        if not buf_h:
            return
        # ONE file, both arrays, written once and renamed. Nothing is appended
        # to a vector file, so the hashes and the vectors cannot drift apart.
        # np.savez APPENDS .npz to a name that does not end in it, so a temp
        # called "...npz.tmp" is written as "...npz.tmp.npz" and the rename
        # then fails on a file that was never there. Hand it an open handle,
        # which it writes verbatim.
        tmp = os.path.join(a.out, "shard-{:04d}.tmp".format(shard_i))
        with open(tmp, "wb") as fh:
            np.savez(fh, hash=np.array(buf_h),
                     vec=np.array(buf_v, dtype=np.float16))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, os.path.join(a.out, "shard-{:04d}.npz".format(shard_i)))
        print("  wrote shard-{:04d}.npz  {:,} vectors".format(shard_i, len(buf_h)),
              flush=True)
        shard_i += 1
        buf_h, buf_v = [], []

    for s in range(0, len(todo), a.batch):
        chunk = todo[s:s + a.batch]
        try:
            vecs = embed([v for _, v in chunk], key)
        except Exception as e:                                   # noqa: BLE001
            fail += len(chunk)
            print("  batch at {} FAILED: {}".format(s, str(e)[:120]), flush=True)
            continue
        buf_h.extend(h for h, _ in chunk)
        buf_v.extend(vecs)
        n += len(chunk)
        spent_chars += sum(len(v) for _, v in chunk)
        if len(buf_h) >= a.shard_size:
            flush_shard()
        spent = (spent_chars / 4 / 1e6) * PER_M
        if n % 1000 < a.batch:
            rate = n / max(time.time() - t0, 1e-9)
            print("  {:,}/{:,}  ${:.2f}  {:.0f}/s  ~{:.0f} min left".format(
                n, len(todo), spent, rate, (len(todo) - n) / max(rate, 1e-9) / 60),
                flush=True)
        if spent >= a.max_usd:
            print("  CEILING ${:.2f} reached - stopping".format(a.max_usd))
            break
    flush_shard()

    spent = (spent_chars / 4 / 1e6) * PER_M
    print()
    print("embedded {:,} in {:.0f} min, {:,} failed, MEASURED ${:.2f}".format(
        n, (time.time() - t0) / 60, fail, spent))
    print("vectors in {}".format(a.out))
    print()
    print('Ask it something: embed_descriptions.py --ask "..."')
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
