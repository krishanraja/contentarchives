r"""One row per file in the library, carrying everything known about it.

    python master_sheet.py                  # rebuild and report coverage
    python master_sheet.py --coverage-only  # report without rewriting

THE PROBLEM THIS SOLVES

The library's knowledge was in three files that could not be joined.
INVENTORY.csv is keyed on LibraryPath and carries the technical facts - EXIF,
camera, dimensions, duration, GPS. ORIGIN-MAP.csv is keyed on LibraryPath and
carries provenance. content_tags.csv is keyed on CONTENT HASH and carries
everything a model or a human has judged: kind, people, subject, keep,
sensitivity, setting, place, era.

Path and hash are different keys, INVENTORY.csv had no hash column, and so the
enrichment could not be attached to an inventory row at all. Every classification
run was filling a store that nothing could read back against the library.

WHERE THE JOIN KEY CAME FROM

MIGRATION-HASHES.csv, written by migrate_library.py while copying the library to
the new disk on 2026-09-11: one row per file, path and size and blake2b-256,
computed from the bytes as they were read. store.content_hash() is the same
computation - blake2b, 32-byte digest, whole file - so the two agree by
construction rather than by luck. 73,198 rows for 73,198 files.

That map is seeded into HASH-INDEX.csv and maintained from there. A file the
index does not know is hashed once and remembered, so a fresh ingest costs its
own bytes and not the library's.

THE POINT OF THE COVERAGE REPORT

Krish's framing: getting this sheet to 100% is the mission, and the swipe game,
the image recognition and everything else exist to fill columns in it. So the
run ends by printing what percentage of files have each field, and what the
weakest column is. A number that goes up is the measure of progress; nothing
else in this project is.

NOTHING HERE IS HAND-MAINTAINED. It is rebuilt from the library, the hash index,
the inventory, the origin map and the enrichment store, all of which are
themselves generated. Edit an input, not this.
"""

from __future__ import annotations

import argparse
import collections
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
sys.path.insert(0, r"D:\_PhotoAudit\scripts")

try:
    import paths as P
    AUDIT, ROOT = P.AUDIT, P.ROOT
except Exception:                                                # noqa: BLE001
    AUDIT, ROOT = r"D:\_PhotoAudit", r"D:\ContentLibrary"

STORE = r"D:\_enrichment"
HASH_INDEX = os.path.join(AUDIT, "HASH-INDEX.csv")
MIGRATION = os.path.join(AUDIT, "MIGRATION-HASHES.csv")
INVENTORY = os.path.join(AUDIT, "INVENTORY.csv")
ORIGINS = os.path.join(AUDIT, "ORIGIN-MAP.csv")
TAGS = os.path.join(STORE, "content_tags.csv")
OUT = os.path.join(AUDIT, "MASTER.csv")

# Which opinion wins when several have judged the same file. A human always
# wins, and that is not a formality - it is the only ground truth here.
#
# The model order came from a bake-off scored against a "reference" built by
# majority vote of the other models. On 2026-09-12 Krish looked at the files
# where that consensus said the stored label was wrong, and the stored label was
# right: 366 files Gemini called "graphic" are screenshots of a maps app, and
# both challenger models agreed with each other about it. Two models agreeing is
# correlated error, not evidence. The caveat was written down when the scorer
# was built and it took a human ten seconds to prove.
#
# So a model no longer silently overrules another model on `kind`. Where they
# differ the disagreement is CARRIED into the sheet - see KindDisputed - and a
# human settles it. 366 files is a short session with the swipe game and ends
# the argument permanently, which is better than either model winning it.
SOURCE_RANK = {"human": 0, "google/gemini-3.1-flash-lite": 1,
               "google/gemini-3.5-flash-lite": 2, "model:haiku": 3}
# Fields where a model disagreeing with another model is recorded rather than
# resolved. Only `kind` so far, because only `kind` has been shown to need it.
CONTESTED = {"kind"}

# Long-format tag names differ between passes: Haiku wrote people_count, the
# live classifier writes people. Normalise on read rather than rewriting the
# store, which is append-only history.
TAG_ALIAS = {"people_count": "people"}

IMAGE_EXT = {"jpg", "jpeg", "png", "heic", "heif", "gif", "webp", "bmp",
             "tif", "tiff", "dng", "cr2", "cr3", "nef", "arw", "raf"}
VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "m4v", "3gp", "webm", "wmv", "mpg",
             "mpeg", "mts", "m2ts", "mod", "vob", "flv"}
# Field -> the kinds of file it can apply to. Anything absent applies to all.
APPLIES = {"Duration": {"video"},
           "Make": {"image", "video"}, "Model": {"image", "video"},
           "Width": {"image", "video"}, "Height": {"image", "video"}}
# Geotags exist only if the camera wrote them. This can never reach 100% and is
# reported separately so it does not drag the mission number down for ever.
OPPORTUNISTIC = {"Lat", "Lon", "place"}

ENRICH = ["kind", "people", "subject", "keep", "sensitivity", "setting",
          "place", "era"]
TECH = ["Bytes", "Ext", "DateTaken", "DateSource", "Make", "Model",
        "Width", "Height", "Duration", "Lat", "Lon"]
COLS = (["LibraryPath", "Hash", "Side", "Year", "Month"] + TECH
        + ["OriginFolder", "SourceRoot", "OriginPath"]
        + ENRICH + ["KindAlt", "KindDisputed", "EnrichedBy", "Confidence"])


def lp(p: str) -> str:
    pre = chr(92) * 2 + "?" + chr(92)
    return p if p.startswith(pre) else pre + p


def read_csv(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def load_hash_index() -> dict:
    """path -> (size, hash), seeded from the migration's own record."""
    idx = {}
    for src in (MIGRATION, HASH_INDEX):
        if not os.path.exists(src):
            continue
        with open(src, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.reader(f):
                if len(r) >= 3:
                    try:
                        idx[r[0].lower()] = (int(r[1]), r[2])
                    except ValueError:
                        continue
    return idx


def enrichment() -> dict:
    """hash -> {field: (value, source, confidence)}, best source winning.

    For a field in CONTESTED, every distinct opinion is kept so the sheet can
    show that the models differ rather than picking one and looking certain.
    """
    best: dict = collections.defaultdict(dict)
    alts: dict = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in read_csv(TAGS):
        h = r.get("hash")
        tag = TAG_ALIAS.get(r.get("tag", ""), r.get("tag", ""))
        if not h or tag not in ENRICH:
            continue
        src = r.get("source", "")
        rank = SOURCE_RANK.get(src, 9)
        cur = best[h].get(tag)
        if cur is None or rank < cur[3]:
            try:
                conf = float(r.get("confidence") or 0)
            except ValueError:
                conf = 0.0
            best[h][tag] = (r.get("value", ""), src, conf, rank)
        if tag in CONTESTED:
            alts[h][tag][r.get("value", "")] = src
    for h, fields in alts.items():
        for tag, opinions in fields.items():
            if len(opinions) > 1:
                chosen = best[h].get(tag, ("",))[0]
                other = [v for v in opinions if v != chosen]
                best[h]["_alt_" + tag] = (";".join(sorted(other)),
                                          ";".join(sorted(opinions[v]
                                                          for v in other)),
                                          0.0, 9)
    return best


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coverage-only", action="store_true")
    a = ap.parse_args()

    files = []
    for dp, _, fns in os.walk(ROOT):
        for fn in fns:
            files.append(os.path.join(dp, fn))
    if not files:
        sys.exit("no files found under " + ROOT
                 + " - that is a broken walk, not an empty library")
    print("library      : {:,} files".format(len(files)))

    idx = load_hash_index()
    print("hash index   : {:,} paths known".format(len(idx)))

    inv = {r["LibraryPath"].lower(): r for r in read_csv(INVENTORY)
           if r.get("LibraryPath")}
    # ORIGIN-MAP.csv stores RELATIVE, pre-restructure paths for most of its
    # rows - "Library\2019\..." against the old root. Joining raw matched
    # zero of 110,652 rows and reported OriginPath as 0% coverage, which read
    # like missing data rather than a broken key. paths.resolve() exists for
    # precisely this and was not being called.
    org = {}
    for r in read_csv(ORIGINS):
        q = r.get("LibraryPath")
        if not q:
            continue
        try:
            q = P.resolve(q)
        except Exception:                                        # noqa: BLE001
            pass
        org[q.lower()] = r
    enr = enrichment()
    print("inventory    : {:,} rows".format(len(inv)))
    print("origin map   : {:,} rows".format(len(org)))
    print("enrichment   : {:,} hashes carry at least one field".format(len(enr)))

    import hashlib
    new_hashes = []

    def hash_of(p: str, size: int) -> str:
        k = p.lower()
        hit = idx.get(k)
        if hit and hit[0] == size:
            return hit[1]
        h = hashlib.blake2b(digest_size=32)
        try:
            with open(lp(p), "rb") as f:
                for b in iter(lambda: f.read(8 << 20), b""):
                    h.update(b)
        except OSError:
            return ""
        v = h.hexdigest()
        idx[k] = (size, v)
        new_hashes.append([p, size, v])
        return v

    cov = collections.Counter()
    denom = collections.Counter()
    rows = 0
    tmp = OUT + ".tmp"
    sink = open(tmp, "w", newline="", encoding="utf-8") if not a.coverage_only \
        else None
    w = csv.writer(sink) if sink else None
    if w:
        w.writerow(COLS)

    for p in files:
        try:
            size = os.path.getsize(lp(p))
        except OSError:
            continue
        rel = os.path.relpath(p, ROOT)
        parts = rel.split(os.sep)
        side = parts[1] if len(parts) > 1 and parts[0] == "Media" else parts[0]
        year = month = ""
        for seg in parts:
            if len(seg) == 4 and seg.isdigit():
                year = seg
            if len(seg) == 7 and seg[:4].isdigit() and seg[4] == "-":
                month = seg
        h = hash_of(p, size)
        iv = inv.get(p.lower(), {})
        ov = org.get(p.lower(), {})
        ev = enr.get(h, {})

        rec = {"LibraryPath": p, "Hash": h, "Side": side,
               "Year": year, "Month": month, "Bytes": size,
               "Ext": os.path.splitext(p)[1].lower().lstrip(".")}
        for c in TECH:
            if c not in rec:
                rec[c] = iv.get(c, "")
        rec["OriginFolder"] = ov.get("OriginFolder", iv.get("OriginFolder", ""))
        rec["SourceRoot"] = ov.get("SourceRoot", iv.get("SourceRoot", ""))
        rec["OriginPath"] = ov.get("OriginPath", "")
        srcs, confs = set(), []
        for c in ENRICH:
            v = ev.get(c)
            rec[c] = v[0] if v else ""
            if v:
                srcs.add(v[1])
                confs.append(v[2])
        alt = ev.get("_alt_kind")
        rec["KindAlt"] = alt[0] if alt else ""
        rec["KindDisputed"] = "1" if alt else ""
        rec["EnrichedBy"] = ";".join(sorted(srcs))
        rec["Confidence"] = "{:.2f}".format(
            sum(confs) / len(confs)) if confs else ""

        # A field only counts against the files it can apply to. Duration is
        # a video property: scoring it over the whole library reported 95% of
        # videos as 14% of everything, which makes the target unreachable by
        # construction and the metric worthless.
        ext = rec["Ext"]
        kinds = {"video" if ext in VIDEO_EXT else
                 "image" if ext in IMAGE_EXT else "other"}
        for c in COLS:
            if c in APPLIES and kinds.isdisjoint(APPLIES[c]):
                continue
            denom[c] += 1
            if str(rec.get(c, "")).strip():
                cov[c] += 1
        rows += 1
        if w:
            w.writerow([rec.get(c, "") for c in COLS])

    if sink:
        sink.close()
        os.replace(tmp, OUT)
        print("wrote        : {}  ({:,} rows)".format(OUT, rows))

    if new_hashes:
        fresh = not os.path.exists(HASH_INDEX)
        with open(HASH_INDEX, "a", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            if fresh:
                wr.writerow(["LibraryPath", "Bytes", "Blake2b256"])
            wr.writerows(new_hashes)
        print("hashed {:,} files not previously indexed".format(len(new_hashes)))

    print("")
    print("COVERAGE - the mission is to make every one of these 100%")
    print("-" * 62)
    order = ["Hash", "Side", "Year", "Month"] + TECH + \
            ["OriginFolder", "SourceRoot", "OriginPath"] + ENRICH
    worst = []
    for c in order:
        d = denom[c] or rows
        pc = 100.0 * cov[c] / max(d, 1)
        bar = "#" * int(pc / 4)
        note = "  (opportunistic)" if c in OPPORTUNISTIC else ""
        scope = "" if d == rows else "  of {:,}".format(d)
        print("  {:<14}{:>7.1f}%  {:<25} {:,}{}{}".format(
            c, pc, bar, cov[c], scope, note))
        if c not in OPPORTUNISTIC:
            worst.append((pc, c))
    worst.sort()
    print("-" * 62)
    goal = [c for c in order if c not in OPPORTUNISTIC]
    num = sum(cov[c] for c in goal)
    den = sum(denom[c] or rows for c in goal)
    print("  overall field completeness: {:.1f}%".format(
        100.0 * num / max(den, 1)))
    print("  (geotags and place are opportunistic - excluded from the target)")
    print("  weakest: " + ", ".join(
        "{} ({:.0f}%)".format(c, pc) for pc, c in worst[:4]))


if __name__ == "__main__":
    main()
