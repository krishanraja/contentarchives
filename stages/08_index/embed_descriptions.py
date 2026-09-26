r"""Embed every description, so the library can be asked in words rather than keywords.

    python embed_descriptions.py                 # report, send nothing
    python embed_descriptions.py --apply
    python embed_descriptions.py --ask "the afternoon everyone was squinting"

    # narrow the meaning-search with the structured facts the index already has
    python embed_descriptions.py --ask "green t-shirt, plain light background" \
        --year 2026 --person Krish
    python embed_descriptions.py --ask "on a beach" --holiday --year 2024-2026
    python embed_descriptions.py --ask "birthday cake" --person Bharti \
        --place Scotland --contact-sheet D:\_out\cake.png

WHY THE FILTERS EXIST

`--ask` alone ranks the WHOLE library by meaning, and "photos of Krish in 2026"
is not a meaning a vector distinguishes from "photos of Krish" - similarity
degrades gracefully rather than failing loudly, so a person-and-year question
answered by meaning alone quietly returns whoever and whenever ranked closest.
The structured fields (`year`, `person`, `place`, `occasion`, `media`, ...)
already exist in `library.db` and answer those parts exactly; this only adds
them as filters applied AFTER the semantic ranking, so a query can do both at
once instead of a human eyeballing which of the top 60 are actually 2026.

VOCABULARY - see build_db.py's own warning before trusting a filter's silence

    --year     files.year, text, exact ('2026') or a range ('2024-2026')
    --person   photo_people.person, substring, case-insensitive. A group
               photo has one row per person in it - this is right for
               "photos WITH Krish in them", not "solo photos of Krish"
    --place    resolved place/region/country, substring, case-insensitive
    --occasion resolved occasion (its own vocabulary: 'everyday', 'travel', ...)
    --holiday  shorthand for --occasion travel, only when --occasion is unset
    --activity resolved activity, substring
    --mood     resolved mood, substring
    --side     Personal or Communal. NOT files.side (that is the top-level
               TREE - Media/Archive/_Review - see sides.py's own warning);
               this reads the path one level down, the same way sides.py does
    --media    files.media: photo / video / other
    --after / --before   files.date_taken, inclusive, 'YYYY-MM-DD' or longer

A filter that finds nothing says so and states how deep it searched - the same
rule `--ask` already followed for description coverage: a narrow answer is
only useful if you can tell it apart from a broken one.

CONTACT SHEET

`--contact-sheet PATH.png` renders the results as a grid of thumbnails (from
`--thumbs`, default `D:\_thumbs`, content-addressed as `{hash[:2]}\{hash}.jpg`
- see backfill_thumbs.py) with a one-line caption per tile, instead of a list
of paths nobody is going to go open one at a time. Requires Pillow; the text
report still prints without it.

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


def parse_year_range(spec):
    """'2026' -> (2026, 2026); '2024-2026' -> (2024, 2026). Raises ValueError."""
    spec = spec.strip()
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return int(lo), int(hi)
    y = int(spec)
    return y, y


def side_of_path(path):
    """Personal or Communal, one level under Media/Archive/_Review - the
    same rule sides.py enforces, kept in sync deliberately rather than
    imported, because this file must run standalone against a read-only
    library.db with no guarantee the rest of the tree is on sys.path."""
    norm = (path or "").replace("\\", "/").lower()
    if "/personal/" in norm:
        return "Personal"
    if "/communal/" in norm:
        return "Communal"
    return None


def fetch_meta(db, h, fields):
    """One row of resolved fields for a hash, only the ones asked for -
    a per-hash lookup, not a join, because the candidate pool this is
    called against is the top of a similarity ranking, not the library."""
    if not fields:
        return {}
    marks = ",".join("?" * len(fields))
    out = {f: None for f in fields}
    for field, value in db.execute(
            "SELECT field, value FROM resolved WHERE hash=? AND field IN ({})"
            .format(marks), (h, *fields)):
        out[field] = value
    return out


def build_filters(a):
    """-> (year_range|None, want_person|None, checks: list of (kind, needle))
    checks is the free-text substring filters against resolved fields that
    don't get their own dedicated lookup path."""
    year_range = parse_year_range(a.year) if a.year else None
    checks = []
    if a.place:
        checks.append(("place", a.place.lower()))
    if a.occasion:
        checks.append(("occasion", a.occasion.lower()))
    elif a.holiday:
        checks.append(("occasion", "travel"))
    if a.activity:
        checks.append(("activity", a.activity.lower()))
    if a.mood:
        checks.append(("mood", a.mood.lower()))
    return year_range, checks


def passes_filters(db, h, path, year, media, a, year_range, checks):
    if year_range and not (year or "").isdigit():
        return False
    if year_range:
        y = int(year)
        if not (year_range[0] <= y <= year_range[1]):
            return False
    if a.media and (media or "").lower() != a.media.lower():
        return False
    if a.side and side_of_path(path) != a.side:
        return False
    if a.person:
        hit = db.execute(
            "SELECT 1 FROM photo_people WHERE hash=? AND person LIKE ? LIMIT 1",
            (h, "%{}%".format(a.person))).fetchone()
        if not hit:
            return False
    if a.after or a.before:
        dt = db.execute(
            "SELECT date_taken FROM files WHERE hash=? AND path=?", (h, path)
        ).fetchone()
        dt = (dt[0] if dt else "") or ""
        if a.after and dt < a.after:
            return False
        if a.before and dt > a.before:
            return False
    if checks:
        need = {field: needle for field, needle in checks}
        got = fetch_meta(db, h, ["place", "region", "country", "occasion",
                                  "activity", "mood"])
        for field, needle in need.items():
            if field == "place":
                blob = " ".join(filter(None, [got.get("place"),
                                               got.get("region"),
                                               got.get("country")])).lower()
            else:
                blob = (got.get(field) or "").lower()
            if needle not in blob:
                return False
    return True


def contact_sheet(out_path, thumbs_dir, rows, cols=6, tile=220):
    """rows: [(hash, caption)]. Writes a PNG grid; needs Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  (Pillow not installed - skipping --contact-sheet; "
              "pip install Pillow)")
        return False
    if not rows:
        print("  (nothing to put on a contact sheet)")
        return False
    n = len(rows)
    cols = max(1, min(cols, n))
    grid_rows = (n + cols - 1) // cols
    cap_h = 34
    sheet = Image.new("RGB", (cols * tile, grid_rows * (tile + cap_h)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:                                            # noqa: BLE001
        font = None
    missing = 0
    for i, (h, caption) in enumerate(rows):
        col, row = i % cols, i // cols
        x, y = col * tile, row * (tile + cap_h)
        thumb_path = os.path.join(thumbs_dir, h[:2], h + ".jpg")
        if os.path.exists(thumb_path):
            try:
                im = Image.open(thumb_path)
                im.thumbnail((tile, tile))
                px = x + (tile - im.width) // 2
                py = y + (tile - im.height) // 2
                sheet.paste(im, (px, py))
            except Exception:                                    # noqa: BLE001
                missing += 1
        else:
            missing += 1
            draw.rectangle([x, y, x + tile - 1, y + tile - 1], outline="gray")
        draw.text((x + 4, y + tile + 2), caption[:34], fill="black", font=font)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    sheet.save(out_path)
    print("  contact sheet: {}  ({} tiles, {} thumbnail{} missing)".format(
        out_path, n, missing, "" if missing == 1 else "s"))
    return True


def ask(a):
    """Search by meaning, then narrow by the structured facts the index
    already has. Prints what it could NOT see, every time - coverage AND
    how deep the filters had to dig."""
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
    order = np.argsort(-sims)

    year_range, checks = build_filters(a)
    have_filters = bool(year_range or checks or a.person or a.side
                         or a.media or a.after or a.before)

    db = sqlite3.connect("file:{}?mode=ro".format(a.db.replace("\\", "/")), uri=True)
    total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print('"{}"'.format(a.ask))
    if have_filters:
        bits = []
        if a.year: bits.append("year={}".format(a.year))
        if a.person: bits.append("person~{}".format(a.person))
        if a.place: bits.append("place~{}".format(a.place))
        if a.occasion: bits.append("occasion~{}".format(a.occasion))
        elif a.holiday: bits.append("occasion~travel (--holiday)")
        if a.activity: bits.append("activity~{}".format(a.activity))
        if a.mood: bits.append("mood~{}".format(a.mood))
        if a.side: bits.append("side={}".format(a.side))
        if a.media: bits.append("media={}".format(a.media))
        if a.after: bits.append("after={}".format(a.after))
        if a.before: bits.append("before={}".format(a.before))
        print("  filters: {}".format(", ".join(bits)))
    print()

    results = []
    scanned = 0
    scan_cap = min(a.scan, len(order))
    for i in order[:scan_cap]:
        scanned += 1
        h = str(H[i])
        row = db.execute(
            "SELECT path, year, media FROM files WHERE hash=? LIMIT 1",
            (h,)).fetchone()
        if not row:
            continue
        path, year, media = row
        if have_filters and not passes_filters(
                db, h, path, year, media, a, year_range, checks):
            continue
        results.append((h, float(sims[i]), path, year))
        if len(results) >= a.top:
            break

    for h, sim, path, year in results:
        desc = db.execute(
            "SELECT value FROM resolved WHERE hash=? AND field='description'",
            (h,)).fetchone()
        print("  {:.3f}  {}  {}".format(sim, (year or "????"),
                                         os.path.basename(path)[:46]))
        if desc:
            print("         {}".format(desc[0][:104]))

    print()
    if have_filters:
        note = ("  matched {:,} of {:,} requested, scanning the top {:,} of {:,} "
                 "described files by meaning.".format(
                     len(results), a.top, scanned, len(H)))
        if len(results) < a.top and scanned >= scan_cap:
            note += (" Ran out of similarity ranking before the filters were "
                      "satisfied - the rest of the library may still have "
                      "matches; widen with --scan {:,} or loosen a filter."
                      .format(scan_cap * 4))
        print(note)
    # THE COVERAGE IS PART OF THE ANSWER, NOT A FOOTNOTE. A result that is
    # silently blind to a third of the library is this project's recurring
    # failure in a friendlier costume.
    print("  searched {:,} of {:,} files ({:.1f}%). The rest have no description "
          "and cannot match anything.".format(len(H), total, 100.0 * len(H) / total))

    if a.contact_sheet:
        rows = [(h, "{}  {}".format(year or "????", os.path.basename(path)))
                for h, sim, path, year in results]
        contact_sheet(a.contact_sheet, a.thumbs, rows)

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
    ap.add_argument("--scan", type=int, default=2000,
                     help="--ask with a filter: how deep into the similarity "
                          "ranking to look for --top matches (default 2000)")
    ap.add_argument("--year", default="",
                     help="--ask filter: '2026' or a range '2024-2026'")
    ap.add_argument("--person", default="",
                     help="--ask filter: substring against photo_people, "
                          "e.g. Krish")
    ap.add_argument("--place", default="",
                     help="--ask filter: substring against place/region/country")
    ap.add_argument("--occasion", default="",
                     help="--ask filter: substring against resolved occasion")
    ap.add_argument("--holiday", action="store_true",
                     help="--ask filter: shorthand for --occasion travel")
    ap.add_argument("--activity", default="",
                     help="--ask filter: substring against resolved activity")
    ap.add_argument("--mood", default="",
                     help="--ask filter: substring against resolved mood")
    ap.add_argument("--side", choices=["Personal", "Communal"], default="",
                     help="--ask filter: one level under Media/Archive/"
                          "_Review - NOT files.side, see sides.py")
    ap.add_argument("--media", choices=["photo", "video", "other"], default="",
                     help="--ask filter: files.media")
    ap.add_argument("--after", default="",
                     help="--ask filter: date_taken >= this (YYYY-MM-DD)")
    ap.add_argument("--before", default="",
                     help="--ask filter: date_taken <= this (YYYY-MM-DD)")
    ap.add_argument("--contact-sheet", default="",
                     help="--ask: write the results as a thumbnail grid PNG "
                          "here instead of only printing paths (needs Pillow)")
    ap.add_argument("--thumbs", default=r"D:\_thumbs",
                     help="--contact-sheet: content-addressed thumbnail cache")
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
