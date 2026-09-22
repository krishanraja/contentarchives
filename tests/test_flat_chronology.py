r"""The chronology is ONE LEVEL DEEP, and the writers must agree with the library.

    python tests\test_flat_chronology.py

WHY THIS EXISTS

`flatten_months.py` collapsed `YYYY\YYYY-MM\` to `YYYY\` on both copies on
2026-09-21, on Krish's instruction: *"I do not want folders by the Month"*.
66,047 files moved on each copy. But the collapse was applied to the LIBRARY
and not to the three writers that PLACE files into it - `autopilot.place`,
`autopilot`'s tree walk and `ingest_tree.py` all still built
`os.path.join(LIB, y, f"{y}-{m}")`, and `redate_videos.py` did too.

Nothing failed, which is the point. The next ingest would have rebuilt the
month level one file at a time, into folders that no index, no mirror arm and
no reader looks in - RESUME.md: *"Anything written from now on that assumes a
`YYYY-MM` level will put files where nothing looks for them."* A file placed
somewhere nothing reads is not an error anyone sees; it is a success report
over an invisible file, the same shape as learning 51.

So the layout is pinned here rather than trusted to four copies of a join, and
the collision convention is pinned with it: `flatten_months.py` resolved 70
same-year name collisions by PREFIXING the month (`05_001.jpg`), Krish's choice
over a suffix because it keeps the month rather than discarding it. A second
convention for the same layout is a convention nobody can read.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401

import autopilot as ap                                   # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<58} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def main():
    d = tempfile.mkdtemp(prefix="flatchron-")
    lib = os.path.join(d, "Pending-Segmentation")
    nodate = os.path.join(d, "NoDate")
    ap.LIB, ap.NODATE = lib, nodate

    # 1. A dated file lands in YYYY\, with NO month level anywhere beneath it.
    dest = ap.dated_dest("a.jpg", "2017", "02")
    check("a dated file lands directly in its year folder",
          os.path.relpath(dest, lib), os.path.join("2017", "a.jpg"))
    check("no month folder is created", os.path.isdir(os.path.join(lib, "2017-02")), False)
    check("no month folder inside the year either",
          os.path.isdir(os.path.join(lib, "2017", "2017-02")), False)

    # 2. A collision inside the year takes the MONTH PREFIX, not a __1 suffix.
    #    This is the convention flatten_months.py already wrote into the library.
    open(dest, "w").close()
    dest2 = ap.dated_dest("a.jpg", "2017", "05")
    check("a same-year collision is prefixed with its month",
          os.path.basename(dest2), "05_a.jpg")
    check("the prefixed file is still in the year folder, not a month folder",
          os.path.relpath(dest2, lib), os.path.join("2017", "05_a.jpg"))

    # 3. Only when the prefixed name is ALSO taken does the numeric suffix
    #    apply. It is the last resort, not the first move - if it fired first
    #    the month would be thrown away, which is what Krish chose against.
    open(dest2, "w").close()
    dest3 = ap.dated_dest("a.jpg", "2017", "05")
    check("a second collision on the same month falls back to a suffix",
          os.path.basename(dest3), "05_a__1.jpg")

    # 4. Two different months keep their own prefixes and never overwrite.
    open(dest3, "w").close()
    dest4 = ap.dated_dest("a.jpg", "2017", "11")
    check("a different month gets its own prefix, overwriting nothing",
          os.path.basename(dest4), "11_a.jpg")

    # 5. An undated file goes to NoDate, which has no year level at all.
    check("an undated file goes to NoDate with no year folder",
          os.path.relpath(ap.dated_dest("b.jpg", "", ""), nodate), "b.jpg")

    # 6. THE REGRESSION ITSELF. No writer may rebuild the month level. This
    #    reads the source, because the bug was four separate copies of one
    #    join and a behavioural test of one of them would have passed while
    #    the other three stayed broken.
    writers = [
        os.path.join(ROOT, "stages", "02_ingest", "autopilot.py"),
        os.path.join(ROOT, "stages", "02_ingest", "ingest_tree.py"),
        os.path.join(ROOT, "stages", "03_dating", "redate_videos.py"),
    ]
    offenders = []
    for w in writers:
        for n, line in enumerate(open(w, encoding="utf-8"), 1):
            if "{y}-{m}" in line and "os.path.join" in line:
                offenders.append("{}:{}".format(os.path.basename(w), n))
    check("no writer joins a YYYY-MM folder onto the library root",
          offenders, [])

    # 7. THE SIDECAR ASYMMETRY. `autopilot` read Takeout's `.json` sidecars and
    #    `ingest_tree` passed `{}`, so the SAME export dated differently
    #    depending on which tool ingested it - and for HEIC and re-encoded video
    #    the sidecar is the only date there is (`ym_for` reads EXIF for jpg
    #    only, the container clock for video only). One parser now serves both.
    sc = os.path.join(d, "export")
    os.makedirs(sc, exist_ok=True)
    io_write = lambda n, o: open(os.path.join(sc, n), "w", encoding="utf-8").write(json.dumps(o))
    # Keyed on `title`, not on the sidecar's own filename: Takeout truncates and
    # suffixes those, so matching on them loses files in silence.
    io_write("IMG_9.HEIC.supplemental-metadata.json",
             {"title": "IMG_9.HEIC", "photoTakenTime": {"timestamp": "1700000000"}})
    io_write("not-a-sidecar.json", {"hello": "world"})
    m = ap.sidecar_map_from_tree(sc)
    check("a sidecar is keyed by its title, not its own filename",
          m, {"img_9.heic": "1700000000"})

    check("a json that is not a sidecar is ignored, not crashed on",
          ap.parse_sidecar(b'{"hello":"world"}'), None)
    check("unparseable bytes are ignored, not crashed on",
          ap.parse_sidecar(bytes([0]) + b"not json"), None)

    # The date must actually reach ym_for - a map nobody reads is the bug.
    y, mo = ap.ym_for(os.path.join(sc, "IMG_9.HEIC"), "IMG_9.HEIC", sc, m)
    check("the sidecar date is what dates a HEIC with no other signal", y, "2023")

    print()
    if FAILURES:
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
