r"""Give every file that carries GPS a place name, without asking anybody.

    python geocode_library.py             # count what would be written
    python geocode_library.py --apply

WHY

Measured 2026-09-12 across 82,635 inventory rows: Lat/Lon on 33.6%, any place
name on 4.4%. So roughly 24,000 files knew exactly where they were taken and
nobody had ever turned that into a word. The rule this follows is: never spend a
human question, or a model call, on something already sitting in the file.

WHAT IT WRITES

Into the enrichment store, keyed on content hash like everything else:

    country   always, when there are coordinates
    region    always (the admin-1 area: Scotland, Maharashtra, New South Wales)
    place     ONLY when the nearest populated place is within --max-km

That last distinction matters. The index knows populated places, so a photo
taken on a hillside resolves to the nearest village and the distance says how
far. Writing "Edinburgh" on a picture taken 60 km from Edinburgh would be a
plain falsehood, while "Scotland, United Kingdom" stays true at any distance. So
the precise field is withheld when it cannot be justified and the coarse ones
are not.

These are written with source "geonames", which outranks the vision models in
master_sheet's SOURCE_RANK and loses to "human". A coordinate from the camera is
better evidence of location than a model's guess from pixels, and worse evidence
than Krish saying where he was.

IT IS DERIVED, SO IT IS DISPOSABLE

Nothing here is irreplaceable: delete every geonames row and re-run, and the
same answers come back for free. That is what licenses the bulk write path and
the re-runnability, and it is the opposite of the answers journal, which records
judgements that exist nowhere else.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
HERE = os.path.dirname(os.path.abspath(__file__))


from geocode import Geocoder                      # noqa: E402
from store import Store                           # noqa: E402
import master_sheet as MS                         # noqa: E402

SOURCE = "geonames"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", default=MS.INVENTORY)
    ap.add_argument("--store", default=MS.STORE)
    ap.add_argument("--data", default=None, help="GeoNames dir")
    ap.add_argument("--max-km", type=float, default=25.0,
                    help="beyond this, write region and country but not place")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.inventory):
        raise SystemExit("no inventory at " + a.inventory)

    idx = MS.load_hash_index()
    print("hash index   : {:,} paths".format(len(idx)))

    # Which hashes already carry a geonames answer? Resume rather than re-append.
    done = set()
    tags_path = os.path.join(a.store, "content_tags.csv")
    if os.path.exists(tags_path):
        with io.open(tags_path, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("source") == SOURCE and r.get("tag") == "country":
                    done.add(r.get("hash"))
    print("already geocoded: {:,} hashes".format(len(done)))

    coords, hashes = [], []
    seen = set()
    rows = 0
    no_hash = 0
    with io.open(a.inventory, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            rows += 1
            lat, lon = (r.get("Lat") or "").strip(), (r.get("Lon") or "").strip()
            if not lat or not lon:
                continue
            try:
                fl, fo = float(lat), float(lon)
            except ValueError:
                continue
            if not (-90.0 <= fl <= 90.0 and -180.0 <= fo <= 180.0):
                continue
            # (0,0) is the Gulf of Guinea and is what a broken writer emits.
            if fl == 0.0 and fo == 0.0:
                continue
            hit = idx.get((r.get("LibraryPath") or "").lower())
            if not hit:
                no_hash += 1
                continue
            h = hit[1]
            if h in done or h in seen:
                continue
            seen.add(h)
            coords.append((fl, fo))
            hashes.append(h)

    print("inventory    : {:,} rows".format(rows))
    print("with usable coordinates and a known hash: {:,}".format(len(hashes)))
    if no_hash:
        print("  ({:,} had coordinates but no hash to key on)".format(no_hash))
    if not hashes:
        print("nothing to do.")
        return

    g = Geocoder(a.data) if a.data else Geocoder()
    found = g.lookup_many(coords)

    near = sum(1 for r in found if r["km"] <= a.max_km)
    print("nearest place within {:g} km: {:,} ({:.1f}%)".format(
        a.max_km, near, 100.0 * near / len(found)))

    countries = collections.Counter(r["country"] for r in found)
    print()
    print("top countries:")
    for c, n in countries.most_common(12):
        print("   {:<28} {:>7,}".format(c, n))
    print()
    places = collections.Counter(
        r["name"] for r in found if r["km"] <= a.max_km)
    print("top places:")
    for c, n in places.most_common(12):
        print("   {:<28} {:>7,}".format(c, n))

    if not a.apply:
        print()
        print("dry run - nothing written. Re-run with --apply.")
        return

    out = []
    for h, r in zip(hashes, found):
        out.append((h, "country", r["country"], SOURCE, 1.0))
        if r["region"]:
            out.append((h, "region", r["region"], SOURCE, 1.0))
        if r["km"] <= a.max_km:
            # Confidence falls off with distance: touching the town is 1.0, at
            # the limit it is 0.5. A reader can then prefer the close ones.
            conf = max(0.5, 1.0 - (r["km"] / (2.0 * a.max_km)))
            out.append((h, "place", r["name"], SOURCE, conf))

    n = Store(a.store).tag_many(out)
    print()
    print("wrote {:,} tag rows for {:,} files".format(n, len(hashes)))


if __name__ == "__main__":
    main()
