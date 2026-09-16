r"""Turn coordinates into place names, offline and for ever.

    python geocode.py --build          # build the index from the GeoNames dump
    python geocode.py 55.9533 -3.1883  # -> Edinburgh, Scotland, United Kingdom

WHY THIS IS NOT AN API CALL

A third of this library carries GPS from the camera and almost none of it
carried a place name: 27,738 files with coordinates against 3,604 with any
place. That is a fact already sitting in the files, needing no model, no human
and no network - so it should cost nothing and never expire. An online geocoder
would bill per lookup, rate-limit a 27,000-file backfill, send a person's
movements to a third party, and stop working the day the key lapses. The
GeoNames dump is a few megabytes, is CC-BY licensed, and answers in microseconds
for ever.

WHY THE NEAREST PLACE IS COMPUTED IN THREE DIMENSIONS

The obvious implementation - a KD-tree over (lat, lon) in degrees - is wrong
twice. A degree of longitude is 111 km at the equator and 0 km at the pole, so
Euclidean distance in degrees is not distance on the ground; and the tree has a
seam at the antimeridian, where +179.9 and -179.9 are adjacent in reality and
maximally far apart in the index. Projecting onto the unit sphere first makes
Euclidean nearest-neighbour exactly great-circle nearest-neighbour, with no seam
and no distortion. Chord length is monotonic in arc length, so the nearest point
is the same point either way.

WHAT IT DOES NOT DO

It names the nearest populated place, not the place you were standing. A photo
in open countryside resolves to the nearest village, and the returned distance
says how far that is - so a caller can refuse to label anything more than, say,
25 km out rather than claiming a precision it does not have.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import os
import zipfile

import numpy as np

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - puts every stage, guards/ and the package root on sys.path
DEFAULT_DATA = os.environ.get("GEONAMES_DIR", r"D:\_enrichment\geonames")
INDEX_NPY = "places-xyz.npy"
INDEX_CSV = "places.csv"
EARTH_KM = 6371.0088


def _admin1(data_dir: str) -> dict:
    """('GB','SCT') -> 'Scotland'"""
    out = {}
    p = os.path.join(data_dir, "admin1.txt")
    if not os.path.exists(p):
        return out
    with io.open(p, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and "." in parts[0]:
                country, code = parts[0].split(".", 1)
                out[(country, code)] = parts[1]
    return out


def _countries(data_dir: str) -> dict:
    """'GB' -> 'United Kingdom'"""
    out = {}
    p = os.path.join(data_dir, "countryInfo.txt")
    if not os.path.exists(p):
        return out
    with io.open(p, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 5:
                out[parts[0]] = parts[4]
    return out


def build(data_dir: str = DEFAULT_DATA) -> int:
    """Read the GeoNames dump and write the two index files. Idempotent."""
    src = os.path.join(data_dir, "cities1000.zip")
    if not os.path.exists(src):
        raise SystemExit(
            "no cities1000.zip in " + data_dir + "\n"
            "get it from https://download.geonames.org/export/dump/cities1000.zip\n"
            "(admin1CodesASCII.txt and countryInfo.txt from the same place give\n"
            " readable region and country names; without them the codes are used)")
    a1 = _admin1(data_dir)
    cc = _countries(data_dir)

    lats, lons, rows = [], [], []
    with zipfile.ZipFile(src) as z:
        name = [n for n in z.namelist() if n.endswith(".txt")][0]
        with z.open(name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                f = line.rstrip("\n").split("\t")
                if len(f) < 15:
                    continue
                try:
                    lat, lon = float(f[4]), float(f[5])
                except ValueError:
                    continue
                country_code, admin1_code = f[8], f[10]
                lats.append(lat)
                lons.append(lon)
                rows.append((f[1],
                             a1.get((country_code, admin1_code), admin1_code),
                             cc.get(country_code, country_code),
                             country_code,
                             f[14] or "0"))

    lat = np.radians(np.asarray(lats, dtype=np.float64))
    lon = np.radians(np.asarray(lons, dtype=np.float64))
    xyz = np.empty((len(rows), 3), dtype=np.float32)
    xyz[:, 0] = np.cos(lat) * np.cos(lon)
    xyz[:, 1] = np.cos(lat) * np.sin(lon)
    xyz[:, 2] = np.sin(lat)

    np.save(os.path.join(data_dir, INDEX_NPY), xyz)
    with io.open(os.path.join(data_dir, INDEX_CSV), "w",
                 encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "region", "country", "cc", "population", "lat", "lon"])
        for r, la, lo in zip(rows, lats, lons):
            w.writerow(list(r) + [la, lo])
    print("indexed {:,} populated places from {}".format(len(rows), src))
    return len(rows)


class Geocoder:
    """Nearest populated place to a coordinate. Load once, query freely."""

    def __init__(self, data_dir: str = DEFAULT_DATA):
        from scipy.spatial import cKDTree
        npy = os.path.join(data_dir, INDEX_NPY)
        if not os.path.exists(npy):
            build(data_dir)
        self.xyz = np.load(npy)
        self.rows = []
        with io.open(os.path.join(data_dir, INDEX_CSV),
                     encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                self.rows.append(r)
        self.tree = cKDTree(self.xyz)

    @staticmethod
    def _to_xyz(lat, lon):
        rlat, rlon = np.radians(lat), np.radians(lon)
        return np.column_stack([np.cos(rlat) * np.cos(rlon),
                                np.cos(rlat) * np.sin(rlon),
                                np.sin(rlat)])

    def _row(self, i: int, chord: float) -> dict:
        km = EARTH_KM * 2.0 * math.asin(min(float(chord), 2.0) / 2.0)
        r = self.rows[int(i)]
        return {"name": r["name"], "region": r["region"],
                "country": r["country"], "km": round(km, 1)}

    def lookup(self, lat: float, lon: float) -> dict:
        """-> {name, region, country, km}. km is how far the answer actually is."""
        chord, i = self.tree.query(self._to_xyz([lat], [lon])[0])
        return self._row(i, chord)

    def lookup_many(self, coords) -> list:
        """Batched: one tree query for all of them, far faster than a loop."""
        pts = np.asarray(coords, dtype=np.float64)
        chord, idx = self.tree.query(self._to_xyz(pts[:, 0], pts[:, 1]))
        return [self._row(i, d) for i, d in zip(idx, chord)]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--build", action="store_true", help="build the index and exit")
    ap.add_argument("coords", nargs="*", type=float, help="lat lon")
    a = ap.parse_args()
    if a.build:
        build(a.data)
        return
    if len(a.coords) != 2:
        ap.error("give a lat and a lon, or --build")
    g = Geocoder(a.data)
    print("{name}, {region}, {country}  ({km} km away)".format(
        **g.lookup(a.coords[0], a.coords[1])))


if __name__ == "__main__":
    main()
