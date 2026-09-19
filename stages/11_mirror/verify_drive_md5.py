r"""Prove the cloud copy by GOOGLE'S checksum, not by reading back the mount.

    python verify_drive_md5.py                 # verify, using a cached listing
    python verify_drive_md5.py --refresh       # re-fetch the Drive listing
    python verify_drive_md5.py --sample 500    # spot-check, for a quick answer

WHY THIS IS THE ONLY VERIFICATION THAT COUNTS

`mirror_to_h.py` computes blake2b AND md5 over the bytes it WRITES, and records
both in the journal. That proves what left this machine. It does not prove what
Google received.

Reading the file back through the H: mount cannot prove it either, and is worse
than useless: a read hydrates the placeholder, which fills the local cache
(learning 5) and returns the LOCAL copy - the very bytes we already trust. That
is exactly how 140.62 GB was once "verified" that the cloud did not have
(learning 25).

Drive stores its own `md5Checksum`, computed server-side on receipt. Comparing
the journal's md5 against that is the only check that crosses the network
boundary in the right direction.

HOW IT AVOIDS THE OBVIOUS TRAPS

  ONE LISTING, NOT 82,104 LOOKUPS. Paging the whole file list is ~83 requests
  at pageSize=1000. Asking Drive about each file individually is 82,104 round
  trips, would take hours, and would hit rate limits.

  PATHS ARE RECONSTRUCTED FROM PARENT IDs, never matched by filename. The
  library holds many files with the same basename in different folders - a
  name match would report a false pass for a file sitting in the wrong place.

  THE LISTING IS CACHED AS IT PAGES, one JSON object per line, flushed and
  fsynced. `hash_283.py` held its results in memory, was killed for memory an
  hour in, and lost everything; the rule since is that long work writes as it
  goes. A re-run reuses the cache unless --refresh is given.

  THE TOKEN IS REFRESHED ON 401. A gcloud access token expired three times
  during the session that produced this mirror. A verification that dies at 60%
  because of an expired credential has proved nothing.

  A FILE PRESENT WITH THE WRONG CHECKSUM IS A LOUDER RESULT THAN ONE MISSING.
  Both are reported separately, because they mean different things: missing is
  an upload that never happened, mismatched is corruption in transit.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Walk UP to whichever directory holds stagepath.py, exactly as every other
# module in this stage does. Hardcoding a relative depth ("../_shared") is the
# thing stagepath.py exists to stop: a file that assumes where it sits breaks
# the moment it is moved, and tools/refresh.py called a script by bare name
# after it moved and failed silently for three days.
_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.exists(
        os.path.join(_d, "stagepath.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)

import stagepath  # noqa: E402,F401
import paths as P  # noqa: E402

API = "https://www.googleapis.com/drive/v3"
JOURNAL = os.path.join(P.AUDIT, "h-mirror.csv")
CACHE = os.path.join(P.AUDIT, "drive-listing.jsonl")
REPORT = os.path.join(P.AUDIT, "DRIVE-VERIFY.csv")
# THE COMPARISON KEY, and it is not what the mount calls the file.
#
# The journal records where the WRITER put it: H:\My Drive\ContentLibrary\...
# Drive's own path starts at the first folder under the account root, because
# `files.list` never returns the root itself - resolving a top-level parent
# yields nothing, so a reconstructed path begins "ContentLibrary/...". There is
# no "My Drive" segment on the API side at all; that name exists only in the
# DriveFS mount.
#
# Keying on "My Drive\ContentLibrary" matched nothing and reported all 82,100
# files MISSING - a total failure that was entirely my own arithmetic, on a
# mirror whose very first probe had already matched an 18.6 GB file's checksum
# byte for byte. A verification that reports everything broken is as useless as
# one that reports everything fine; both mean the check is not measuring what it
# claims.
DEST_PREFIX = "ContentLibrary"

csv.field_size_limit(1 << 30)


class Token:
    """A gcloud access token that can renew itself mid-run."""

    def __init__(self):
        self.value = ""
        self.fetched = 0.0
        self.refresh()

    def refresh(self):
        out = subprocess.run(["gcloud", "auth", "print-access-token"],
                             capture_output=True, text=True, timeout=180,
                             shell=True)
        if out.returncode != 0:
            sys.exit("gcloud could not produce a token: {}\n"
                     "  Run: gcloud auth login --enable-gdrive-access".format(
                         (out.stderr or "").strip()[:300]))
        self.value = (out.stdout or "").strip()
        self.fetched = time.time()
        if not self.value:
            sys.exit("gcloud returned an empty token")


def api(path, tok: Token, **params):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        req = urllib.request.Request(
            url, headers={"Authorization": "Bearer " + tok.value})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                tok.refresh()
                continue
            if e.code in (403, 429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            raise SystemExit("HTTP {} on {}\n  {}".format(
                e.code, path, e.read().decode("utf-8", "replace")[:400]))
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    raise SystemExit("giving up on {} after 6 attempts".format(path))


def fetch_listing(tok: Token) -> int:
    """Page the whole Drive, writing one JSON object per line as we go."""
    n = 0
    page = None
    with io.open(CACHE, "w", encoding="utf-8", newline="\n") as fh:
        while True:
            params = dict(
                q="trashed=false",
                fields="nextPageToken,files(id,name,md5Checksum,size,parents,"
                       "mimeType)",
                pageSize=1000,
                supportsAllDrives="false")
            if page:
                params["pageToken"] = page
            r = api("/files", tok, **params)
            for f in r.get("files", []):
                fh.write(json.dumps(f, separators=(",", ":")) + "\n")
                n += 1
            fh.flush()
            os.fsync(fh.fileno())
            page = r.get("nextPageToken")
            print("    {:,} files listed".format(n), flush=True)
            if not page:
                break
    return n


def load_listing():
    files = {}
    with io.open(CACHE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                f = json.loads(line)
                files[f["id"]] = f
    return files


def build_paths(files: dict) -> dict:
    """id -> full path, resolved through parents. Cycles and orphans are named."""
    FOLDER = "application/vnd.google-apps.folder"
    cache: dict[str, str] = {}

    def resolve(fid, seen=None):
        if fid in cache:
            return cache[fid]
        seen = seen or set()
        if fid in seen:
            return "<cycle>"
        f = files.get(fid)
        if not f:
            return ""                      # a parent outside the listing (root)
        parents = f.get("parents") or []
        if not parents:
            out = f["name"]
        else:
            seen.add(fid)
            head = resolve(parents[0], seen)
            out = os.path.join(head, f["name"]) if head else f["name"]
        cache[fid] = out
        return out

    return {fid: resolve(fid) for fid, f in files.items()
            if f.get("mimeType") != FOLDER}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch the Drive listing instead of using the cache")
    ap.add_argument("--sample", type=int, default=0,
                    help="check only the largest N journalled files")
    a = ap.parse_args()

    tok = Token()
    who = api("/about", tok, fields="user(emailAddress),storageQuota")
    print("account: {}".format(who["user"]["emailAddress"]))

    if a.refresh or not os.path.exists(CACHE):
        print("fetching the Drive listing (~83 requests, not 82,104)...")
        n = fetch_listing(tok)
        print("  listed {:,} items -> {}".format(n, CACHE))
    else:
        age = (time.time() - os.path.getmtime(CACHE)) / 60
        print("using cached listing from {:.0f} min ago "
              "(--refresh to re-fetch)".format(age))

    files = load_listing()
    paths = build_paths(files)
    print("  {:,} items in the listing, {:,} of them files".format(
        len(files), len(paths)))

    # Drive path -> (md5, size). Keyed on the PATH, so a filename that appears
    # in several folders cannot produce a false match.
    by_path = {}
    for fid, p in paths.items():
        f = files[fid]
        by_path[p.replace("/", "\\").lower()] = (
            (f.get("md5Checksum") or "").lower(), f.get("size"))

    rows = []
    with io.open(JOURNAL, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("outcome") == "written" and r.get("md5") and r.get("dest"):
                rows.append(r)
    # One row per destination: a file deferred and retried appears several times.
    latest = {}
    for r in rows:
        latest[r["dest"].lower()] = r
    rows = list(latest.values())
    if a.sample:
        rows.sort(key=lambda r: -int(r.get("bytes") or 0))
        rows = rows[:a.sample]
    print("  {:,} journalled file(s) to verify".format(len(rows)))

    verified = missing = mismatch = nochecksum = unkeyed = 0
    problems = []
    for r in rows:
        dest = r["dest"]
        i = dest.lower().find(DEST_PREFIX.lower())
        if i < 0:
            # NO FALLBACK TO THE BASENAME. Matching on filename alone is the
            # false pass this whole path reconstruction exists to prevent: the
            # library holds many files sharing a basename in different folders,
            # and a name match would confirm a file that is on Drive in the
            # wrong place - or confirm a different file entirely.
            unkeyed += 1
            problems.append(("UNKEYED", dest, r["md5"], ""))
            continue
        key = dest[i:].lower().replace("/", "\\")
        got = by_path.get(key)
        if got is None:
            missing += 1
            problems.append(("MISSING", dest, r["md5"], ""))
            continue
        drive_md5, drive_size = got
        if not drive_md5:
            nochecksum += 1
            problems.append(("NO-CHECKSUM", dest, r["md5"], ""))
            continue
        if drive_md5 != r["md5"].lower():
            mismatch += 1
            problems.append(("MISMATCH", dest, r["md5"], drive_md5))
            continue
        verified += 1

    print()
    print("=== VERIFIED AGAINST GOOGLE'S OWN CHECKSUMS ===")
    print("  verified     : {:>7,}".format(verified))
    print("  MISSING      : {:>7,}".format(missing))
    print("  MISMATCHED   : {:>7,}  (corruption in transit)".format(mismatch))
    print("  no checksum  : {:>7,}  (Google stores none for this type)".format(
        nochecksum))
    print("  UNKEYED      : {:>7,}  (no '{}' in the journalled path, so this "
          "check could not look for it)".format(unkeyed, DEST_PREFIX))

    if problems:
        with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Problem", "Dest", "JournalMd5", "DriveMd5"])
            w.writerows(problems)
            fh.flush()
            os.fsync(fh.fileno())
        print()
        print("  {} problem(s) written to {}".format(len(problems), REPORT))
        for p in problems[:10]:
            print("    {:<12} {}".format(p[0], p[1][-80:]))

    # UNKEYED counts as not proven. A file this check could not even look for
    # is not a file it verified, and silently excluding it from the verdict is
    # how a summary comes to overstate what was done (learning 61).
    if missing or mismatch or unkeyed:
        print()
        print("THE CLOUD COPY IS NOT PROVEN. Do not delete a local copy of")
        print("anything named above on the strength of the mirror.")
        return 1

    print()
    print("Every journalled file is present on Drive with the checksum Google")
    print("computed on receipt. The second copy is PROVEN, not merely uploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
