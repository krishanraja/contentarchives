"""Survey every library file over 200 MB and classify it for compression."""
import os, re, csv, subprocess, json
from collections import defaultdict

LIB = "D:/PhotoLibrary"
BS = chr(92)
THRESH = 200 * 1024 * 1024
FFPROBE = (r"C:\Users\user\AppData\Local\Microsoft\WinGet\Packages"
           r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
           r"\ffmpeg-8.1.1-full_build\bin\ffprobe.exe")

# Device signatures - filename or path gives it away
DEVICE = [
    ("GoPro",        re.compile(r"^(GOPR|GH01|GX01|GP\d)", re.I)),
    ("DJI drone",    re.compile(r"^DJI[_-]", re.I)),
    ("Sony",         re.compile(r"^(DSC|MAH\d|C\d{4}|\d{5}MTS)", re.I)),
    ("Canon/Nikon",  re.compile(r"^(IMG_|MVI_|DSCN|_MG_)", re.I)),
    ("Phone camera", re.compile(r"^(PXL_|VID[_-]|\d{8}[_-]\d{6})", re.I)),
    ("Screen rec",   re.compile(r"Screen[_ ]?Recording|1VRecorder", re.I)),
    ("WhatsApp",     re.compile(r"WhatsApp", re.I)),
]
ACTIVITY = re.compile(r"scuba|dive|diving|snorkel|ski|surf|wanaka|queenstown|india|"
                      r"val.?d.?isere|uk december|holiday|wedding|safari|trek", re.I)

rows = []
for dp, _, fns in os.walk(LIB):
    for fn in fns:
        p = os.path.join(dp, fn)
        try:
            s = os.path.getsize(p)
        except OSError:
            continue
        if s < THRESH:
            continue
        dev = "unknown"
        for label, rx in DEVICE:
            if rx.match(fn) or rx.search(p):
                dev = label
                break
        rows.append({"path": p, "bytes": s, "device": dev,
                     "activity": bool(ACTIVITY.search(p))})

rows.sort(key=lambda r: -r["bytes"])
total = sum(r["bytes"] for r in rows)
print(f"LIBRARY FILES OVER 200 MB")
print("=" * 76)
print(f"  count {len(rows):,}    total {total/1024**3:.1f} GB "
      f"({100*total/max(1,sum(1 for _ in [1])):.0f})" if False else
      f"  count {len(rows):,}    total {total/1024**3:.1f} GB")

by = defaultdict(lambda: [0, 0])
for r in rows:
    b = by[r["device"]]
    b[0] += 1
    b[1] += r["bytes"]
print()
print("BY DEVICE SIGNATURE")
print("-" * 76)
for k in sorted(by, key=lambda x: -by[x][1]):
    print(f"  {k:<16} {by[k][0]:>5,} files  {by[k][1]/1024**3:>7.2f} GB")

act = [r for r in rows if r["activity"]]
print()
print(f"  with an activity/trip word in the path: {len(act):,} files, "
      f"{sum(r['bytes'] for r in act)/1024**3:.2f} GB")

# probe the top files for codec/resolution - tells us the compression headroom
print()
print("TOP 25 BY SIZE  (with codec / resolution / duration)")
print("-" * 76)
for r in rows[:25]:
    codec = res = dur = "?"
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", r["path"]],
            capture_output=True, text=True, timeout=60).stdout
        j = json.loads(out or "{}")
        v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
        if v:
            codec = v.get("codec_name", "?")
            res = f"{v.get('width','?')}x{v.get('height','?')}"
        d = j.get("format", {}).get("duration")
        if d:
            dur = f"{float(d)/60:.1f}m"
    except Exception:
        pass
    rel = r["path"][len(LIB) + 1:]
    print(f"  {r['bytes']/1024**3:>6.2f} GB {codec:<6} {res:<10} {dur:>6}  "
          f"{r['device']:<13} {rel[:44]}")

with open("D:/_PhotoAudit/big-files.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Path", "Bytes", "Device", "ActivityWord"])
    for r in rows:
        w.writerow([r["path"], r["bytes"], r["device"], r["activity"]])
print()
print("written: D:/_PhotoAudit/big-files.csv")
