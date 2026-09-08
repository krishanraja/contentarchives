r"""Find GoPro/DJI clips that are the same footage twice, before ingesting 144 GB.

Byte-identical duplicates are already handled - a hash catches those. This looks
for the harder cases, where two files hold the same moment but no bytes in
common:

  RE-ENCODES   same footage, different bitrate or container. Identical duration
               and resolution, very different size.
  TRIMS        one clip is a cut of another. Shorter duration, same recording
               timestamp, same camera.
  PROXIES      .lrv (GoPro) and .lrf (DJI) low-resolution companions generated
               beside their own original. 27.6 GB of the 268 GB on H:.
  CHAPTERS     GoPro splits long recordings into GH01xxxx, GH02xxxx... These are
               NOT duplicates - they are consecutive parts of one recording, and
               deleting the "extra" ones loses the second half of the take.

That last category is why this reports rather than deletes. The naming that
signals a chapter and the naming that signals a duplicate look alike, and
getting it wrong quietly removes the end of a memory.

WHAT IT USES

ffprobe: duration, resolution, bitrate, creation time, and the camera's own
model string. Two files from one camera with the same creation timestamp and
duration are the same take; the bigger one is the original.

METADATA ONLY ON A CLOUD MOUNT

Reading a file on H: hydrates it and can hang (learnings 5 and 15). So when
--source points at H:, this reads names and sizes only, and says so. Full
probing happens once files are local.

    python video_variants.py --source "H:\My Drive\_photo-consolidation\from-gopro-2024"
    python video_variants.py --source "D:\..." --probe
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import subprocess
import sys

FFPROBE = (r"C:\Users\user\AppData\Local\Microsoft\WinGet\Packages"
           r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
           r"\ffmpeg-8.1.1-full_build\bin\ffprobe.exe")
OUT = r"D:\_PhotoAudit\VIDEO-VARIANTS.csv"

VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".m2ts", ".mod", ".webm"}
PROXY = {".lrv", ".lrf", ".thm"}

# GoPro: GH01xxxx / GX01xxxx - the 01 is the CHAPTER, xxxx is the recording.
GOPRO = re.compile(r"^(g[hx])(\d{2})(\d{4})\.", re.I)
# DJI: DJI_0001.MP4, DJI_20240612_1200_01.MP4
DJI = re.compile(r"^(dji)[_-](\d+)", re.I)


def probe(path: str) -> dict:
    try:
        r = subprocess.run([FFPROBE, "-v", "quiet", "-print_format", "json",
                            "-show_format", "-show_streams", path],
                           capture_output=True, timeout=40)
        d = json.loads(r.stdout or b"{}")
    except Exception:
        return {}
    out: dict = {}
    fmt = d.get("format", {})
    try:
        out["duration"] = round(float(fmt.get("duration", 0)), 1)
    except Exception:
        pass
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    out["created"] = str(tags.get("creation_time", ""))[:19]
    out["model"] = tags.get("model") or tags.get("com.apple.quicktime.model", "")
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            out["w"], out["h"] = s.get("width"), s.get("height")
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--probe", action="store_true",
                    help="run ffprobe - only for LOCAL sources")
    a = ap.parse_args()

    on_cloud = a.source[:1].upper() in ("H", "G")
    if on_cloud and a.probe:
        sys.exit("refusing to probe a cloud mount: reading hydrates files and can "
                 "hang (learnings 5 and 15). Copy locally first.")

    files, proxies = [], []
    for dp, dns, fns in os.walk(a.source):
        for fn in fns:
            e = os.path.splitext(fn)[1].lower()
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            (proxies if e in PROXY else files if e in VIDEO else []).append((p, fn, sz))

    print(f"  video files : {len(files):,}  ({sum(s for _,_,s in files)/1024**3:.1f} GB)")
    print(f"  proxies     : {len(proxies):,}  ({sum(s for _,_,s in proxies)/1024**3:.1f} GB)"
          f"   <- never ingest these")

    # ---- chapters: same recording id, different chapter number ----
    recordings = collections.defaultdict(list)
    for p, fn, sz in files:
        m = GOPRO.match(fn)
        if m:
            recordings[("gopro", m.group(3))].append((int(m.group(2)), p, sz))
    multi = {k: v for k, v in recordings.items() if len(v) > 1}
    if multi:
        tot = sum(s for v in multi.values() for _, _, s in v)
        print(f"\n  GoPro multi-chapter recordings: {len(multi):,} "
              f"({sum(len(v) for v in multi.values()):,} files, {tot/1024**3:.1f} GB)")
        print("    NOT duplicates - consecutive parts of one take. Keep all.")
        for k, v in list(multi.items())[:3]:
            print(f"      recording {k[1]}: chapters {sorted(c for c,_,_ in v)}")

    # ---- same-size candidates, the cheap signal available without probing ----
    by_size = collections.defaultdict(list)
    for p, fn, sz in files:
        by_size[sz].append(p)
    dupe_size = {s: v for s, v in by_size.items() if len(v) > 1}
    if dupe_size:
        waste = sum(s * (len(v) - 1) for s, v in dupe_size.items())
        print(f"\n  identical SIZE (likely byte-duplicates): {len(dupe_size):,} groups, "
              f"{waste/1024**3:.1f} GB beyond one copy each")

    rows = []
    if a.probe:
        print("\n  probing durations...", flush=True)
        meta = {}
        for i, (p, fn, sz) in enumerate(files, 1):
            meta[p] = probe(p)
            if i % 25 == 0:
                print(f"    {i:,}/{len(files):,}", flush=True)
        # same camera + same creation time = same take
        takes = collections.defaultdict(list)
        for p, fn, sz in files:
            m = meta.get(p, {})
            key = (m.get("model", ""), m.get("created", ""))
            if key[1]:
                takes[key].append((p, sz, m.get("duration", 0), m.get("w"), m.get("h")))
        variants = {k: v for k, v in takes.items() if len(v) > 1}
        print(f"\n  same camera AND same creation timestamp: {len(variants):,} groups")
        for k, v in list(variants.items())[:6]:
            print(f"    {k[1]}  {k[0][:24]}")
            for p, sz, dur, w, h in sorted(v, key=lambda x: -x[1]):
                print(f"       {sz/1e6:8.1f} MB  {dur:7.1f}s  {w}x{h}  {os.path.basename(p)[:44]}")
            for p, sz, dur, w, h in v:
                rows.append(["same-take", k[0], k[1], p, sz, dur, f"{w}x{h}"])

    for p, fn, sz in proxies:
        rows.append(["proxy", "", "", p, sz, "", ""])
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Class", "Model", "Created", "Path", "Bytes", "Duration", "Res"])
        w.writerows(rows)
    print(f"\n  report: {OUT}")
    print("  Nothing is deleted here. Chapters look like duplicates and are not;")
    print("  that judgement stays with a human.")


if __name__ == "__main__":
    main()
