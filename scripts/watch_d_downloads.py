r"""Watch downloads landing on D: for the drive's known failure signature.

D: has previously corrupted partial files under sustained parallel write: three
concurrent downloads made the partials SHRINK - 19.8 GB back to 18.5 GB - while
writing at 0 MB/min. Nothing errored. The download simply went backwards, which
is the same signature the retired E: drive produced before it was abandoned.

So the two things worth alarming on are a partial file that gets SMALLER, and one
that stops growing entirely. Either one, caught in the first minutes, costs a
restart; caught at 19.8 GB it costs a download attempt against Google's limit of
five.

Silence means healthy. Every line printed is something to act on.
"""
from __future__ import annotations
import glob, os, sys, time

WATCH_GLOBS = [r"D:\*.crdownload", r"D:\Takeout\*.crdownload",
               r"D:\*.zip.part",   r"D:\Takeout\*.zip.part"]
DONE_GLOBS  = [r"D:\takeout-*.zip", r"D:\Takeout\takeout-*.zip"]
POLL = 60
STALL_POLLS = 3          # 3 minutes of zero growth
LOW_FREE_GB = 40

prev: dict[str, int] = {}
stall: dict[str, int] = {}
seen_done: set[str] = set()
warned_space = False

def say(msg: str) -> None:
    print(msg, flush=True)

say("watching D: for shrinking or stalled downloads (silence = healthy)")

while True:
    partials = []
    for g in WATCH_GLOBS:
        partials.extend(glob.glob(g))
    for p in partials:
        b = os.path.basename(p)
        try:
            sz = os.path.getsize(p)
        except OSError:
            continue
        was = prev.get(b)
        if was is not None:
            if sz < was:
                say(f"!! SHRINKING on D: {b}  {was/1e9:.2f} GB -> {sz/1e9:.2f} GB  "
                    f"- this is the documented corruption signature. Stop the download.")
                stall[b] = 0
            elif sz == was:
                stall[b] = stall.get(b, 0) + 1
                if stall[b] == STALL_POLLS:
                    say(f"!! STALLED on D: {b} at {sz/1e9:.2f} GB for "
                        f"{STALL_POLLS} minutes (0 MB/min) - same signature, check it.")
            else:
                stall[b] = 0
        prev[b] = sz

    for g in DONE_GLOBS:
        for p in glob.glob(g):
            b = os.path.basename(p)
            if b not in seen_done:
                seen_done.add(b)
                try:
                    say(f"DOWNLOAD COMPLETE on D: {b} ({os.path.getsize(p)/1e9:.1f} GB)")
                except OSError:
                    pass

    try:
        import shutil
        free_gb = shutil.disk_usage("D:/").free / 1024**3
        if free_gb < LOW_FREE_GB and not warned_space:
            say(f"!! D: FREE SPACE LOW: {free_gb:.1f} GB")
            warned_space = True
        elif free_gb >= LOW_FREE_GB * 1.5:
            warned_space = False
    except Exception:
        pass

    time.sleep(POLL)
