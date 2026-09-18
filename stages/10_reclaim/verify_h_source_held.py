r"""Before deleting 501.5 GB from H:, prove the library holds it.

Krish, 2026-09-18: *"clear the photo consolidation first as there are at least 2
copies of that content elsewhere"*.

Very likely true - that folder was the SOURCE of the ingest. But this project's
deletion rule is that a surviving copy is PROVEN at the moment of deletion, not
asserted beforehand, and every near-miss here came from a deletion justified by
something that was true earlier. `guarded_delete.py` puts it plainly:
"Everything else raises. There is no third path."

Right now D:\ContentLibrary is the ONLY complete local copy - E: is the stale
predecessor, 8,908 files and 81 GB short - so "at least 2 copies" needs testing
rather than taking on trust.

HOW, WITHOUT HYDRATING 501 GB OF PLACEHOLDERS

Reading files through the mount hydrates them and fills C: (learning 5), so
nothing here opens an H: file. Three metadata-only passes, strongest first:

  1. PROVENANCE. ORIGIN-MAP.csv records OriginPath and SourceRoot for every
     library file. If an H: file appears as an OriginPath, the library traces
     itself back to that exact file. This is evidence, not inference.
  2. NAME + SIZE against the library's own index.
  3. SIZE alone - weak, reported separately, never counted as held.

Anything unmatched by all three is written out for review. Deletes nothing.
"""
import collections
import csv
import io
import os
import sqlite3
import sys

REPO = r"C:\Users\krish\dev\contentarchives"
sys.path.insert(0, REPO)
import stagepath  # noqa: E402,F401
import paths as P                                                 # noqa: E402

csv.field_size_limit(10 * 1024 * 1024)


def main() -> int:
    SRC = os.path.join(P.H_ROOT)          # H:\My Drive\_photo-consolidation
    OUT = os.path.join(P.AUDIT, "H-SOURCE-NOT-HELD.csv")

    print("source: {}".format(SRC))
    if not os.path.isdir(SRC):
        sys.exit("STOPPING: {} is not reachable.".format(SRC))

    # --- 1. what is on H:, metadata only -----------------------------------
    hfiles = []
    for dp, dns, fns in os.walk(SRC):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                hfiles.append((p, os.path.getsize(p)))
            except OSError:
                hfiles.append((p, -1))
    print("files on H: {:,}   bytes {:,}".format(
        len(hfiles), sum(s for _, s in hfiles if s > 0)))

    # --- 2. the library's own index ----------------------------------------
    db = sqlite3.connect("file:{}?mode=ro".format(
        os.path.join(P.AUDIT, "library.db").replace("\\", "/")), uri=True)
    lib_ns = set()          # (lowername, size)
    lib_sizes = collections.Counter()
    for path, nbytes in db.execute("select path, bytes from files"):
        if nbytes is None:
            continue
        lib_ns.add((os.path.basename(path or "").lower(), nbytes))
        lib_sizes[nbytes] += 1
    db.close()
    print("library index: {:,} (name,size) keys   {:,} distinct sizes".format(
        len(lib_ns), len(lib_sizes)))

    # --- 3. provenance from the origin map ---------------------------------
    origin_paths = set()
    roots = collections.Counter()
    omap = os.path.join(P.AUDIT, "ORIGIN-MAP.csv")
    if os.path.exists(omap):
        with io.open(omap, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                op = (r.get("OriginPath") or "").replace("/", "\\")
                sr = (r.get("SourceRoot") or "").replace("/", "\\")
                if op:
                    origin_paths.add(op.lower())
                    origin_paths.add(os.path.basename(op).lower())
                if sr:
                    roots[sr] += 1
    print("origin map: {:,} origin keys".format(len(origin_paths)))
    print()
    print("=== which SourceRoots does the library trace back to? (top 12) ===")
    for k, v in roots.most_common(12):
        print("  {:>7,}  {}".format(v, k[:78]))

    # --- 4. classify every H: file -----------------------------------------
    held_prov = held_ns = size_only = unmatched = 0
    rows = []
    for p, s in hfiles:
        base = os.path.basename(p).lower()
        if p.lower() in origin_paths or base in origin_paths:
            held_prov += 1
            continue
        if (base, s) in lib_ns:
            held_ns += 1
            continue
        if s in lib_sizes:
            size_only += 1
            rows.append((p, s, "size matches the library but the name does not"))
            continue
        unmatched += 1
        rows.append((p, s, "NO match in the library by provenance, name+size or size"))

    print()
    print("=== is each H: file accounted for in the library? ===")
    print("  traced by PROVENANCE (origin map)      {:>7,}".format(held_prov))
    print("  matched by NAME + SIZE                 {:>7,}".format(held_ns))
    print("  size matches only - NOT proof          {:>7,}".format(size_only))
    print("  NO match at all                        {:>7,}".format(unmatched))
    print("  ------------------------------------------------")
    print("  proven held                            {:>7,}  ({:.1f}%)".format(
        held_prov + held_ns,
        100.0 * (held_prov + held_ns) / max(len(hfiles), 1)))
    print("  NEEDS A DECISION                       {:>7,}  ({:,} bytes)".format(
        size_only + unmatched, sum(s for _, s, _ in rows if s > 0)))

    if rows:
        tmp = OUT + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["HPath", "Bytes", "Why"])
            for p, s, why in sorted(rows, key=lambda t: -(t[1] or 0)):
                w.writerow([p, s, why])
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, OUT)
        print()
        print("  written: {}".format(OUT))
        print()
        print("  the largest ten:")
        for p, s, why in sorted(rows, key=lambda t: -(t[1] or 0))[:10]:
            print("    {:>13,} b  {}".format(s, p[-72:]))

    print()
    print("NOTHING WAS DELETED. This counted and classified only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
