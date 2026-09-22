r"""autopilot.py - drive PhotoLibrary to being the single canonical deduplicated home.

Work units, in priority order:
  1. ingest D:\E-Drive-Rescue        (rescued E: media)
  2. ingest each completed Takeout archive, streamed member-by-member
  3. stop when no work remains

STREAMING DESIGN: archive members are checked for duplication by SIZE first,
straight from the archive index - no extraction. Only a member whose size
collides with something we already hold is extracted to a temp file for a
head+tail signature comparison. Genuinely new files are extracted once,
straight to their final library path. Peak extra disk = one file + net-new
media, never a full 42 GB unpack.

HARD RULES
  * Never modify or delete anything already in PhotoLibrary.
  * Never delete a source archive until its media count is fully accounted for.
  * Halt if D: < MIN_D or C: < MIN_C free.
  * Everything checkpointed; safe to kill and re-run at any time.
"""
import csv, os, re, sys, json, time, shutil, hashlib, tarfile, zipfile, datetime, struct, contextlib, subprocess
from collections import defaultdict

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.exists(_os.path.join(_d, 'stagepath.py')):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _d)
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives
import paths as P  # noqa: E402
AUDIT   = r"D:\_PhotoAudit"
LIB     = r"D:\ContentLibrary\Media\Pending-Segmentation"
NODATE  = r"D:\ContentLibrary\Media\NoDate"
CAT     = r"D:\ContentLibrary\_Catalog"
STATE   = os.path.join(AUDIT, "autopilot-state.csv")
ADDED   = os.path.join(AUDIT, "autopilot-added.csv")
LOGF    = os.path.join(AUDIT, "autopilot.log")
DUPLOG  = os.path.join(AUDIT, "autopilot-duplicates.csv")
# The no-reingest list, and the record of every refusal made from it.
BLOCKLIST = os.path.join(AUDIT, "PURGED-HASHES.csv")
BLOCKLOG  = os.path.join(AUDIT, "autopilot-blocked.csv")
TMPDIR  = r"D:\_takeout_tmp"

ARCHIVE_DIRS = list(P.SOURCES)
ARCHIVE_RX   = re.compile(r"^takeout[-_].*\.(tgz|tar\.gz|zip)$", re.I)
MIN_D_GB, MIN_C_GB = 25.0, 20.0
BUDGET = float(os.environ.get("AUTOPILOT_BUDGET", "3000"))

PHOTO = {'.jpg','.jpeg','.png','.heic','.heif','.gif','.bmp','.tif','.tiff','.webp','.dng',
         '.cr2','.cr3','.nef','.arw','.raf','.orf','.rw2','.pef','.srw'}
VIDEO = {'.mp4','.mov','.avi','.m2ts','.3gp','.mkv','.wmv','.m4v','.mpg','.mpeg','.webm'}
MEDIA = PHOTO | VIDEO
JUNK_RX = re.compile(r"(^|\\)(\.|_)|thumbnails?\\|print-subscriptions|shared_album_comments"
                     r"|user-generated-memory-titles", re.I)

def log(m):
    line = f"{datetime.datetime.now():%H:%M:%S}  {m}"
    print(line, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass

def lp(p):
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


_stale_candidates = 0   # index entries that would not hash: staleness detector


class DeletionRefused(Exception):
    pass


def safe_remove(path, why):
    """The ONLY way this program may delete anything.

    Hard allowlist. A path is deletable only if it is:
      (a) a scratch extraction under TMPDIR, or
      (b) a Takeout archive whose every member has been accounted for.

    Everything else raises. This exists because a path-substring rule once
    deleted 45 irreplaceable personal files; no rule may ever again decide a
    deletion on the basis of what a path looks like.
    """
    real = os.path.abspath(path.replace("\\\\?\\", ""))
    tmp_root = os.path.abspath(TMPDIR)
    lib_root = os.path.abspath(os.path.dirname(LIB))       # D:\ContentLibrary

    # Structural precondition: scratch must never live inside the library, or the
    # scratch allowlist would become a hole straight through the library guard.
    if tmp_root.lower().startswith(lib_root.lower()):
        raise DeletionRefused(f"REFUSED (TMPDIR is inside the library: {tmp_root})")

    if why == "scratch":
        if not real.lower().startswith(tmp_root.lower()):
            raise DeletionRefused(f"REFUSED (not scratch): {real}")
    elif why == "accounted-archive":
        if real.lower().startswith(lib_root.lower()):
            raise DeletionRefused(f"REFUSED (inside PhotoLibrary): {real}")
        if not re.match(r"^takeout[-_].*\.(zip|tgz|tar\.gz)$",
                        os.path.basename(real), re.I):
            raise DeletionRefused(f"REFUSED (not a takeout archive): {real}")
    else:
        raise DeletionRefused(f"REFUSED (unknown reason '{why}'): {real}")
    os.remove(lp(real))

def free_gb(d):
    try:
        return shutil.disk_usage(d).free / 1024**3
    except OSError:
        return 0.0

def space_ok():
    d, c = free_gb("D:\\"), free_gb("C:\\")
    if d < MIN_D_GB:
        log(f"HALT: D: down to {d:.1f} GB (floor {MIN_D_GB})"); return False
    if c < MIN_C_GB:
        log(f"HALT: C: down to {c:.1f} GB (floor {MIN_C_GB})"); return False
    return True

# ---------- library index ----------
INDEX_CACHE = os.path.join(AUDIT, "lib-index.pickle")


# Every root that holds library content. The index MUST cover all of them.
#
# This used to be (LIB, NODATE) alone - 8,036 files - while Personal\ and
# Communal\ held 60,724, or 88% of the library. apply_split.py created those
# two trees and nothing taught the index they existed, so a dedup candidate
# living in the chronology was invisible: the lookup found nothing and the
# member was filed as new. That is what admitted 21,649 duplicate pairs and
# 207 GB on 2026-09-07, and it is NOT fixed by rebuilding the cache - a fresh
# walk of the wrong roots is still the wrong roots.
#
# _Review is included deliberately: a file moved there was judged not-a-memory,
# and a later ingest offering it again should recognise it rather than quietly
# put it back in the chronology.
# Archive\ and ContentProduction\ were absent, and ingest_tree --dest-root
# writes into both. Measured 2026-09-10: four videos held twice, 22.09 GB,
# separate inodes - present in ContentProduction AND in the chronology, and
# invisible to every dedup pass because the index never looked there. The
# reasoning that puts _Review in this list is the same reasoning: a file already
# filed as produced work or as a document should be RECOGNISED on re-import, not
# quietly admitted a second time somewhere else.
INDEX_ROOTS = [LIB, NODATE,
               r"D:\ContentLibrary\Media\Personal",
               r"D:\ContentLibrary\Media\Communal",
               r"D:\ContentLibrary\_Review",
               r"D:\ContentLibrary\Archive",
               r"D:\ContentLibrary\ContentProduction"]


def _walk_index():
    by_size, ns = defaultdict(list), set()
    for root in INDEX_ROOTS:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    s = os.path.getsize(p)
                except OSError:
                    continue
                by_size[s].append(p)
                ns.add((fn.lower(), s))
    return by_size, ns


def build_index():
    r"""size -> [library paths] and set of (lowername, size).

    Cached, because a full walk of 90k+ files costs most of a pass's life when
    the low-memory watchdog kills us every few minutes. The cache is replayed
    and then brought up to date from autopilot-added.csv.

    THE CACHE IS ONLY VALID WHILE NOTHING MOVES FILES.

    This used to say autopilot-added.csv is "the ONLY thing that adds to the
    library", which is true and was the wrong question. Additions are not the
    only thing that invalidates a path index - MOVES do too, and nothing
    records them here. apply_split.py relocated tens of thousands of files out
    of Library\ into Personal\ and Communal\; every cached path pointing at
    them went stale, silently.

    Measured 2026-09-07: 62.9% of cached paths pointed at files that no longer
    existed. Dedup candidates that will not open hash to None, `None == th` is
    False, and the member is filed as new. 35,114 Takeout members were checked
    against that index and only 382 were caught, admitting roughly 222 GB of
    byte-identical duplicates without a single error being raised.

    So: delete lib-index.pickle after ANY operation that moves library files -
    a split, a reclassification, a manual tidy. The staleness counter in the
    archive dedup will complain if you forget, which is the safety net rather
    than the plan.
    """
    added_n = 0
    if os.path.exists(ADDED):
        with open(ADDED, newline="", encoding="utf-8") as f:
            added_n = sum(1 for _ in f)

    if os.path.exists(INDEX_CACHE):
        try:
            import pickle
            with open(INDEX_CACHE, "rb") as f:
                blob = pickle.load(f)
            # The cache is keyed on how many rows autopilot-added.csv had, and
            # on nothing else - so widening INDEX_ROOTS does not invalidate it.
            # A cache built over five roots would keep being replayed after the
            # list grew to seven, and the two new trees would stay invisible
            # exactly as if the fix had never been made. Record the roots.
            if len(blob) == 4:
                cached_added, cached_roots, by_size, ns = blob
            else:                                   # pre-2026-09-10 cache
                cached_added, by_size, ns = blob
                cached_roots = None
            by_size = defaultdict(list, by_size)
            if cached_roots != list(INDEX_ROOTS):
                log("  index cache was built over different roots, rebuilding")
                raise ValueError("root set changed")
            if cached_added <= added_n:
                # replay only the rows appended since the cache was written
                if cached_added < added_n:
                    with open(ADDED, newline="", encoding="utf-8") as f:
                        for i, row in enumerate(csv.reader(f)):
                            if i < cached_added or not row:
                                continue
                            dest = row[0]
                            try:
                                s = os.path.getsize(dest)
                            except OSError:
                                continue
                            by_size[s].append(dest)
                            ns.add((os.path.basename(dest).lower(), s))
                log(f"  index from cache: {sum(len(v) for v in by_size.values()):,} files "
                    f"(+{added_n - cached_added} replayed)")
                return by_size, ns
        except Exception as e:
            log(f"  index cache unusable ({e}), rebuilding")

    by_size, ns = _walk_index()
    try:
        import pickle
        with open(INDEX_CACHE, "wb") as f:
            pickle.dump((added_n, list(INDEX_ROOTS), dict(by_size), ns),
                        f, protocol=4)
    except Exception as e:
        log(f"  could not write index cache: {e}")
    return by_size, ns

def sig_bytes(b_head, b_tail):
    h = hashlib.blake2b(digest_size=16)
    h.update(b_head)
    if b_tail:
        h.update(b_tail)
    return h.hexdigest()

HASH_CACHE_F = os.path.join(AUDIT, "lib-hashes.csv")
_HASH_CACHE = {}
_HASH_DIRTY = []


def load_hash_cache():
    """Library files never change, so their hashes are cached permanently.
    Without this, every pass re-reads gigabytes to re-derive the same hashes."""
    if not os.path.exists(HASH_CACHE_F):
        return
    try:
        with open(HASH_CACHE_F, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) == 3:
                    _HASH_CACHE[(row[0], int(row[1]))] = row[2]
    except Exception:
        pass


def flush_hash_cache():
    global _HASH_DIRTY
    if not _HASH_DIRTY:
        return
    try:
        with open(HASH_CACHE_F, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(_HASH_DIRTY)
        _HASH_DIRTY = []
    except Exception:
        pass


def full_hash(p, size=None):
    """Whole-file hash. Library files are cached on disk across passes."""
    if size is None:
        try:
            size = os.path.getsize(lp(p))
        except OSError:
            return None
    key = (p, size)
    cached = _HASH_CACHE.get(key)
    if cached:
        return cached
    try:
        h = hashlib.blake2b(digest_size=32)
        with open(lp(p), "rb", buffering=0) as f:
            while True:
                b = f.read(4 << 20)
                if not b:
                    break
                h.update(b)
        v = h.hexdigest()
    except OSError:
        return None
    if p.startswith(LIB) or p.startswith(NODATE):
        _HASH_CACHE[key] = v
        _HASH_DIRTY.append([p, size, v])
        if len(_HASH_DIRTY) >= 50:
            flush_hash_cache()
    return v


def sig_file(p, size):
    try:
        with open(lp(p), "rb", buffering=0) as f:
            head = f.read(262144)
            tail = b""
            if size > 524288:
                f.seek(-262144, os.SEEK_END)
                tail = f.read(262144)
        return sig_bytes(head, tail)
    except OSError:
        return None

# ---------- dates ----------
def date_from_name(name, folder=""):
    for s in (name, folder):
        for rx in (r"(?<!\d)(19|20)(\d{2})(\d{2})(\d{2})[_\-]?(\d{2})(\d{2})(\d{2})(?!\d)",
                   r"(?<!\d)(19|20)(\d{2})[-_.](\d{2})[-_.](\d{2})(?!\d)",
                   r"(?<!\d)(19|20)(\d{2})(\d{2})(\d{2})(?!\d)"):
            m = re.search(rx, s)
            if m:
                y = int(m.group(1) + m.group(2)); mo = int(m.group(3)); d = int(m.group(4))
                if 1 <= mo <= 12 and 1 <= d <= 31 and 1995 <= y <= datetime.date.today().year:
                    return f"{y:04d}", f"{mo:02d}"
    return None, None

def exif_ym(path):
    try:
        with open(lp(path), "rb") as f:
            head = f.read(131072)
    except OSError:
        return None, None
    if head[:2] != b"\xff\xd8":
        return None, None
    i = 2
    while i < len(head) - 4:
        if head[i] != 0xFF:
            i += 1; continue
        mk = head[i+1]
        if mk in (0xD8, 0x01) or 0xD0 <= mk <= 0xD7:
            i += 2; continue
        if mk == 0xDA:
            break
        try:
            ln = struct.unpack(">H", head[i+2:i+4])[0]
        except struct.error:
            break
        seg = head[i+4:i+2+ln]
        if mk == 0xE1 and seg[:6] == b"Exif\x00\x00":
            t = seg[6:]
            try:
                en = "<" if t[:2] == b"II" else ">"
                off = struct.unpack(en+"I", t[4:8])[0]
                for _ in range(3):
                    n = struct.unpack(en+"H", t[off:off+2])[0]
                    nxt = None
                    for k in range(n):
                        e = off+2+k*12
                        tag, typ, cnt = struct.unpack(en+"HHI", t[e:e+8])
                        vo = struct.unpack(en+"I", t[e+8:e+12])[0]
                        if tag in (0x9003, 0x0132) and typ == 2 and cnt >= 19:
                            s = t[vo:vo+19].decode("ascii", "ignore")
                            m = re.match(r"(\d{4}):(\d{2}):(\d{2})", s)
                            if m and 1995 <= int(m.group(1)) <= datetime.date.today().year:
                                return m.group(1), m.group(2)
                        elif tag == 0x8769:
                            nxt = vo
                    if nxt is None:
                        break
                    off = nxt
            except Exception:
                pass
            break
        i += 2 + ln
    return None, None

VIDEO_EXT = ('.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.webm', '.wmv',
             '.mpg', '.mpeg', '.mts', '.m2ts')
BOGUS_DATES = ('1970-01-01', '1904-01-01', '2000-01-01', '1601-01-01')
FFPROBE = P.ffprobe(required=False)


def container_ym(path):
    """The recording time the camera wrote into the container.

    Real evidence about a video, and previously never consulted - which is how a
    phone's five-year video history ended up filed under the single month named
    in the folder it arrived in.
    """
    if not os.path.exists(FFPROBE):
        return None, None
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format",
             "-show_streams", path.replace("\\\\?\\", "")],
            capture_output=True, text=True, timeout=60).stdout
        j = json.loads(out or "{}")
    except Exception:
        return None, None
    cands = []
    tags = (j.get("format") or {}).get("tags") or {}
    for k in ("creation_time", "com.apple.quicktime.creationdate", "date"):
        if tags.get(k):
            cands.append(str(tags[k]))
    for s in j.get("streams", []):
        t = (s.get("tags") or {}).get("creation_time")
        if t:
            cands.append(str(t))
    for c in cands:
        mm = re.match(r"(\d{4})-(\d{2})-(\d{2})", c)
        if not mm or mm.group(0) in BOGUS_DATES:
            continue
        y, mo = int(mm.group(1)), int(mm.group(2))
        if 1995 <= y <= datetime.date.today().year and 1 <= mo <= 12:
            return f"{y:04d}", f"{mo:02d}"
    return None, None


SIDECAR_MAX = 4_000_000   # a Takeout sidecar is a few KB; anything huge is not one


def parse_sidecar(raw):
    """One Takeout sidecar -> (title, photoTakenTime), or None.

    Google exports the real capture time in a `.json` beside the photo, and it
    is the only date a HEIC or a re-encoded video carries once the camera's
    filename has been rewritten - `ym_for` reads EXIF for jpg only and the
    container clock for video only, so for everything else this sidecar IS the
    date. `autopilot` read them from inside the archive; `ingest_tree` passed
    `{}` and never looked, which meant the SAME export dated differently
    depending on which of the two tools ingested it. One parser so they cannot
    disagree again.

    Keyed on the sidecar's `title`, which is the original filename, because the
    sidecar's OWN name is mangled by Takeout (truncated, `.supplemental-meta`,
    `(1)` suffixes) and matching on it loses files silently.
    """
    try:
        d = json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    t = (d.get("photoTakenTime") or {}).get("timestamp")
    ttl = d.get("title") or ""
    if t and ttl:
        return ttl.lower(), t
    return None


def sidecar_map_from_tree(root, lp_fn=None):
    """Build the title -> timestamp map by walking an EXTRACTED export tree."""
    opener = lp_fn or lp
    out = {}
    for dp, _, fns in os.walk(opener(root)):
        for fn in fns:
            if not fn.lower().endswith(".json"):
                continue
            full = os.path.join(dp, fn)
            try:
                if os.path.getsize(full) > SIDECAR_MAX:
                    continue
                with open(full, "rb") as fh:
                    got = parse_sidecar(fh.read())
            except OSError:
                continue
            if got:
                out[got[0]] = got[1]
    return out


def ym_for(tmp_path, name, folder, jsonmap):
    """Date precedence, strongest evidence first.

    The folder name comes LAST, and only as a fallback. It used to be checked in
    the same call as the filename, which silently gave it priority over EXIF and
    over the container clock - so a folder someone named years after the fact
    outranked the camera that took the picture.
    """
    ext = os.path.splitext(name)[1].lower()

    # 1. the camera's own filename
    y, m = date_from_name(name, "")
    if y:
        return y, m

    # 2. what the file itself records
    if ext in ('.jpg', '.jpeg'):
        y, m = exif_ym(tmp_path)
        if y:
            return y, m
    elif ext in VIDEO_EXT:
        y, m = container_ym(tmp_path)
        if y:
            return y, m

    # 3. an export's sidecar metadata
    ts = jsonmap.get(name.lower())
    if ts:
        try:
            d = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
            if 1995 <= d.year <= datetime.date.today().year:
                return f"{d.year:04d}", f"{d.month:02d}"
        except Exception:
            pass

    # 4. only now, the folder someone filed it in - weakest evidence there is
    return date_from_name("", folder)

# ---------- placement ----------
def dated_dest(name, y, m):
    r"""Where a newly dated file goes, and under what name.

    THE CHRONOLOGY IS ONE LEVEL DEEP SINCE 2026-09-21. Krish: *"I do not want
    folders by the Month ... there needs to be no subfolders"*. Every writer in
    this stage still built `LIB\YYYY\YYYY-MM\` after `flatten_months.py`
    collapsed the library to `LIB\YYYY\`, so the next ingest would have
    recreated the month level one file at a time - and a file in a folder
    nothing looks for reports success while being invisible (the same shape as
    learning 51).

    A collision inside the year is settled the way `flatten_months.py` settled
    70 of them, because two conventions for one layout is a convention nobody
    can read: prefix the month (`05_001.jpg`), so the month survives in the
    name rather than being thrown away. Only if THAT is taken does the numeric
    suffix apply, which is the pre-existing last resort and not the first move.
    """
    dest_dir = os.path.join(LIB, y) if y else NODATE
    os.makedirs(lp(dest_dir), exist_ok=True)
    dest = os.path.join(dest_dir, name)
    if y and m and os.path.exists(lp(dest)):
        dest = os.path.join(dest_dir, f"{m}_{name}")
    stem, ext = os.path.splitext(dest)
    n = 0
    while os.path.exists(lp(dest)):
        n += 1
        dest = f"{stem}__{n}{ext}"
    return dest


def place(tmp_path, name, y, m, by_size, ns, size):
    dest = dated_dest(name, y, m)
    shutil.move(lp(tmp_path), lp(dest))
    by_size[size].append(dest)
    ns.add((name.lower(), size))
    return dest

# ---------- state ----------
def load_state():
    done = set()
    if os.path.exists(STATE):
        with open(STATE, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r:
                    done.add(r[0])
    return done

def mark(unit):
    with open(STATE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([unit, datetime.datetime.now().isoformat()])

def record(dest, src, how):
    with open(ADDED, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([dest, src, how])
    with open(os.path.join(CAT, "manifest.csv"), "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([dest, src, how])

# ---------- the no-reingest list ----------
#
# Krish, 2026-09-18: "purge all intimate content forever". 88 hashes were
# destroyed and recorded in PURGED-HASHES.csv, and until now NOTHING READ THAT
# FILE. The blocklist was inert: ten old communal phones, the family albums and
# the VHS conversions are all still to be ingested, and any one of them carrying
# a copy would have re-admitted it silently. "Forever" is a property of the
# ingest, not of the delete.
#
# Keyed on CONTENT, never on a path or a name (learning 1 and learning 57): the
# copy on a phone has a different name, a different folder and a different date.
#
# COST. Hashing every candidate would make every ingest slower for the sake of
# 88 files. Every blocked hash has a known size, so the SIZE gates the hash:
# a file whose size is not in the map is admitted without ever being read, which
# is learning 7 used in the other direction - size rules out, only a hash rules
# in.
_BLOCKED = None          # {size: {hash, ...}}, loaded once
_blocked_count = 0


def blocked_index():
    """{size: {hashes}} from PURGED-HASHES.csv. An absent list is EMPTY, loudly.

    A missing blocklist is not an error - there may be nothing purged yet - but
    it is announced, because "no file" and "no entries" must never look the same
    as a working blocklist that happens to match nothing.
    """
    global _BLOCKED
    if _BLOCKED is not None:
        return _BLOCKED
    _BLOCKED = defaultdict(set)
    if not os.path.exists(BLOCKLIST):
        log(f"  no-reingest list ABSENT at {BLOCKLIST} - nothing is blocked")
        return _BLOCKED
    bad = 0
    with open(BLOCKLIST, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].strip().lower() in ("hash", ""):
                continue
            h = row[0].strip().lower()
            # A size in the Hash column is what a broken writer produced once
            # (learning 60). Count them rather than trusting them.
            if len(h) != 64:
                bad += 1
                continue
            try:
                size = int(row[1]) if len(row) > 1 and str(row[1]).isdigit() else -1
            except (TypeError, ValueError):
                size = -1
            _BLOCKED[size].add(h)
    n = sum(len(v) for v in _BLOCKED.values())
    log(f"  no-reingest list: {n} hash(es) across {len(_BLOCKED)} size(s)")
    if bad:
        log(f"  WARNING: {bad} blocklist row(s) have no 64-hex hash - IGNORED")
    if -1 in _BLOCKED:
        log(f"  NOTE: {len(_BLOCKED[-1])} blocked hash(es) carry no size, so "
            f"every candidate must be hashed against them")
    return _BLOCKED


def is_blocked(path, size, label=None):
    """True if this file's CONTENT is on the no-reingest list.

    Hashes only when the size matches a blocked size (or when a blocked entry
    has no size on record, which cannot be gated and says so at load time).
    Every refusal is journalled: a file that silently vanishes during an ingest
    is indistinguishable from a bug.
    """
    idx = blocked_index()
    if not idx:
        return False
    candidates = set(idx.get(size, ()))
    candidates |= idx.get(-1, set())
    if not candidates:
        return False
    h = full_hash(path, size)
    if h is None:
        # Cannot read it, so cannot clear it. Admitting an unreadable file that
        # matches a blocked SIZE is the one case where being wrong is
        # irreversible, so refuse and say so.
        log(f"  BLOCKED (unhashable, size matches a purged file): {label or path}")
        return True
    if h.lower() not in candidates:
        return False
    global _blocked_count
    _blocked_count += 1
    fresh = not os.path.exists(BLOCKLOG)
    with open(BLOCKLOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(["when", "source", "hash", "bytes"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"),
                    label or path, h.lower(), size])
        f.flush()
        os.fsync(f.fileno())
    log(f"  BLOCKED by the no-reingest list: {label or path}")
    return True


# ---------- ingest a plain folder ----------
def ingest_folder(root, by_size, ns, t0):
    new = dup = 0
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if time.time() - t0 > BUDGET or not space_ok():
                return new, dup, False
            if os.path.splitext(fn)[1].lower() not in MEDIA:
                continue
            src = os.path.join(dp, fn)
            try:
                size = os.path.getsize(src)
            except OSError:
                continue
            if size == 0:
                continue
            # Purged content never comes back, whatever it is called now.
            if is_blocked(src, size):
                continue
            if (fn.lower(), size) in ns:
                dup += 1; continue
            if size in by_size:
                s = sig_file(src, size)
                if s and any(sig_file(c, size) == s for c in by_size[size][:8]):
                    dup += 1; continue
            y, m = ym_for(src, fn, dp, {})
            # same volume -> hardlink, else copy
            dest = dated_dest(fn, y, m)
            try:
                if src[0].upper() == 'D':
                    os.link(lp(src), lp(dest))
                    how = "link"
                else:
                    shutil.copy2(lp(src), lp(dest))
                    how = "copy"
                by_size[size].append(dest); ns.add((fn.lower(), size))
                record(dest, src, how); new += 1
            except Exception as e:
                log(f"  ERR {src}: {e}")
    return new, dup, True

# ---------- ingest an archive, streaming ----------
def ingest_archive(path, by_size, ns, t0):
    os.makedirs(lp(TMPDIR), exist_ok=True)
    new = dup = skipped = errors = media_total = resumed = 0
    jsonmap = {}
    is_zip = path.lower().endswith(".zip")

    # Per-member checkpoint. Without this, a budget stop or a watchdog kill
    # restarts a 40 GB / 3,000-member archive from the beginning and it never
    # finishes. Members already handled are skipped without extraction.
    progdir = os.path.join(AUDIT, "arc-progress")
    os.makedirs(lp(progdir), exist_ok=True)
    progf = os.path.join(progdir, re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(path)) + ".csv")
    done_members = set()
    if os.path.exists(progf):
        with open(progf, newline="", encoding="utf-8") as pf:
            for row in csv.reader(pf):
                if len(row) >= 2:
                    done_members.add(row[0])
    prior = len(done_members)
    if prior:
        log(f"  resuming: {prior:,} members already handled")
    ph = open(progf, "a", newline="", encoding="utf-8")
    pw = csv.writer(ph)

    def handle(name, size, opener):
        """opener() returns a FILE-LIKE OBJECT, never bytes. Members are streamed
        to disk in chunks - reading a whole member into RAM spikes memory by the
        size of the file (Takeout holds multi-GB videos) and gets us killed."""
        nonlocal new, dup, skipped, errors, media_total, resumed
        base = os.path.basename(name)
        ext = os.path.splitext(base)[1].lower()
        if ext == ".json":
            if size > SIDECAR_MAX:
                return
            try:
                with opener() as fh:
                    got = parse_sidecar(fh.read())
                if got:
                    jsonmap[got[0]] = got[1]
            except Exception:
                pass
            return
        if ext not in MEDIA or size == 0 or JUNK_RX.search(name):
            skipped += 1
            return

        media_total += 1
        if name in done_members:      # handled on an earlier pass
            resumed += 1
            return

        # No library file of this exact size -> cannot be a duplicate. Extract it.
        candidates = by_size.get(size) or []

        tmp = os.path.join(TMPDIR, base)
        k = 0
        while os.path.exists(lp(tmp)):
            k += 1
            tmp = os.path.join(TMPDIR, f"{k}_{base}")
        try:
            with opener() as fh, open(lp(tmp), "wb") as out:
                shutil.copyfileobj(fh, out, 4 << 20)   # 4 MB chunks, constant memory
        except Exception as e:
            log(f"  ERR extract {name}: {e}")
            errors += 1
            try:
                safe_remove(tmp, 'scratch')
            except OSError:
                pass
            return

        # Purged content never comes back. Checked HERE rather than before the
        # extract because a member inside an archive has no file to hash until
        # it has been streamed out; the size gate means only a size-matching
        # member is ever hashed for this.
        if is_blocked(tmp, size, label=path + "!" + name):
            try:
                safe_remove(tmp, 'scratch')
            except OSError:
                pass
            skipped += 1
            pw.writerow([name, "blocked"]); ph.flush()
            return

        # Duplicate ONLY if a whole-file hash matches. No name shortcuts.
        if candidates:
            th = full_hash(tmp)
            if th is None:
                log(f"  ERR hash {name}")
                errors += 1
                try: safe_remove(tmp, 'scratch')
                except OSError: pass
                return
            # A candidate that will not hash is a STALE INDEX ENTRY, not a
            # non-match. full_hash returns None there, and `None == th` is
            # False, so the member was silently filed as new. On 2026-09-07
            # the index was 62.9% stale - apply_split.py had MOVED tens of
            # thousands of files out of Library\ and the cache is only
            # replayed from autopilot-added.csv, which records additions and
            # knows nothing about moves. 35,114 Takeout members were checked
            # against it and only 382 were caught, admitting ~222 GB of
            # byte-identical duplicates. Counting these is what makes a stale
            # index announce itself instead of manufacturing duplicates.
            for c in candidates:
                ch = full_hash(c)
                if ch is None:
                    global _stale_candidates
                    _stale_candidates += 1
                    if _stale_candidates in (1, 100, 1000, 10000):
                        log(f"  WARNING: index candidate unreadable ({_stale_candidates} so far) "
                            f"- library index may be STALE, duplicates will be missed: {c}")
                    continue
                if ch == th:
                    try: safe_remove(tmp, 'scratch')
                    except OSError: pass
                    dup += 1
                    with open(DUPLOG, "a", newline="", encoding="utf-8") as df:
                        csv.writer(df).writerow([path + "!" + name, c, size])
                    pw.writerow([name, "dup"]); ph.flush()
                    return

        y, m = ym_for(tmp, base, os.path.dirname(name), jsonmap)
        dest = place(tmp, base, y, m, by_size, ns, size)
        record(dest, path + "!" + name, "copy")
        new += 1
        pw.writerow([name, "new"]); ph.flush()

    if is_zip:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                if time.time() - t0 > BUDGET or not space_ok():
                    ph.close(); return new, dup, skipped, errors, media_total, resumed, False
                handle(info.filename, info.file_size, lambda i=info: z.open(i))
    else:
        with tarfile.open(path, "r|gz") as t:
            for mem in t:
                if not mem.isfile():
                    continue
                if time.time() - t0 > BUDGET or not space_ok():
                    ph.close(); return new, dup, skipped, errors, media_total, resumed, False
                f = t.extractfile(mem)
                if f is None:
                    continue
                handle(mem.name, mem.size, lambda ff=f: contextlib.closing(ff))
    ph.close()
    return new, dup, skipped, errors, media_total, resumed, True

def find_archives():
    out = []
    for d in ARCHIVE_DIRS:
        try:
            for fn in os.listdir(d):
                p = os.path.join(d, fn)
                if not os.path.isfile(p):
                    continue
                if fn.lower().endswith(".crdownload"):
                    continue
                if ARCHIVE_RX.match(fn) or (fn.lower().endswith((".tgz", ".tar.gz")) and "takeout" in fn.lower()):
                    out.append(p)
        except OSError:
            pass
    return sorted(out)

def main():
    t0 = time.time()
    os.makedirs(lp(CAT), exist_ok=True)
    done = load_state()
    log(f"=== autopilot start | D: {free_gb('D:'):.1f} GB  C: {free_gb('C:'):.1f} GB ===")
    load_hash_cache()
    log("building library index...")
    by_size, ns = build_index()
    log(f"library index: {sum(len(v) for v in by_size.values()):,} files")

    # 1. rescued E: media - ONLY once the rescue has finished, otherwise we would
    #    ingest half-written files. The rescue logs one row per verified file.
    if "E-Drive-Rescue" not in done and os.path.exists(r"D:\E-Drive-Rescue"):
        rescue_log = os.path.join(AUDIT, "e-rescue.csv")
        rescued = 0
        if os.path.exists(rescue_log):
            with open(rescue_log, newline="", encoding="utf-8") as f:
                rescued = sum(1 for r in csv.reader(f) if r)
        if rescued < 2363:
            log(f"  E-Drive-Rescue still in progress ({rescued:,}/2,363) - deferring ingest")
        else:
            log("ingesting D:\\E-Drive-Rescue ...")
            n, d, complete = ingest_folder(r"D:\E-Drive-Rescue", by_size, ns, t0)
            log(f"  E-Drive-Rescue: +{n:,} new, {d:,} duplicates")
            if complete:
                mark("E-Drive-Rescue")

    # 2. takeout archives
    for arc in find_archives():
        if time.time() - t0 > BUDGET or not space_ok():
            log("stopping cleanly (budget or space)"); break
        key = os.path.basename(arc)
        if key in done:
            continue
        sz = os.path.getsize(arc) / 1024**3
        log(f"processing {key} ({sz:.1f} GB) ...")
        try:
            n, d, sk, errs, total, res, complete = ingest_archive(arc, by_size, ns, t0)
        except Exception as e:
            log(f"  FAILED {key}: {e}"); continue
        log(f"  {key}: +{n:,} new, {d:,} content-verified duplicates, "
            f"{res:,} already done, {sk:,} non-media skipped, {errs} errors, "
            f"{total:,} media members")

        # An archive is only deleted when EVERY media member provably ended up
        # either placed in the library or byte-identical to a file already in it.
        accounted = (n + d + res == total)
        safe = complete and errs == 0 and accounted
        if not safe:
            log(f"  KEEPING {key}: complete={complete} errors={errs} "
                f"accounted={accounted} ({n}+{d}+{res} vs {total})")
            continue
        mark(key)
        try:
            safe_remove(arc, 'accounted-archive')
            log(f"  verified all {total:,} members -> deleted {key}, freed {sz:.1f} GB")
        except Exception as e:
            log(f"  could not delete {key}: {e}")

    try:
        if os.path.isdir(TMPDIR) and not os.listdir(TMPDIR):
            os.rmdir(lp(TMPDIR))
    except OSError:
        pass
    flush_hash_cache()
    log(f"=== autopilot pass end | D: {free_gb('D:'):.1f} GB  C: {free_gb('C:'):.1f} GB ===")

if __name__ == "__main__":
    main()
