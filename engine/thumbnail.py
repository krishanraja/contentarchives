r"""Make small thumbnails, because image size is what a vision pass actually costs.

Token cost scales with pixel dimensions, not with file size or subject matter.
Sending a 4000x3000 original to a classifier costs several times what a 512px
version costs and answers "is this a screenshot" no better. On 79,300 files that
difference is the whole budget.

So: thumbnail once, locally, then classify from thumbnails. The thumbnails are
also what the swipe game serves to a phone, so the same pass pays for both.

DEPENDENCIES, DELIBERATELY MINIMAL

Pillow if it is installed. If not, ffmpeg - which is already present here for
video probing and will happily resize a JPEG. If neither, the file is skipped
and reported rather than the run failing: a missing thumbnail is a gap, not a
reason to abandon 79,000 others.

VIDEOS get a frame extracted at 10% duration - far enough in to miss a black
lead-in, early enough to be cheap to seek to.

Named by CONTENT HASH, not by source filename. Two paths holding the same bytes
produce one thumbnail and one classification, and a rename upstream changes
nothing here.

    python thumbnail.py --source "D:\ContentLibrary" --out "D:\_thumbs"
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from store import content_hash                                   # noqa: E402

PHOTO = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.bmp', '.tif',
         '.tiff', '.webp'}
VIDEO = {'.mp4', '.mov', '.avi', '.m2ts', '.3gp', '.mkv', '.wmv', '.m4v',
         '.mpg', '.mpeg', '.webm', '.mts'}

FFMPEG = os.environ.get("FFMPEG_PATH") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE_PATH") or "ffprobe"


def lp(p: str) -> str:
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def _pillow(src: str, dst: str, size: int) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(lp(src)) as im:
            im = im.convert("RGB")
            im.thumbnail((size, size))
            im.save(dst, "JPEG", quality=72)
        return True
    except Exception:
        return False


def _ffmpeg_image(src: str, dst: str, size: int) -> bool:
    try:
        r = subprocess.run([FFMPEG, "-y", "-v", "quiet", "-i", src,
                            "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease",
                            "-q:v", "6", dst], capture_output=True, timeout=60)
        return r.returncode == 0 and os.path.exists(dst)
    except Exception:
        return False


def _ffmpeg_video(src: str, dst: str, size: int) -> bool:
    at = 1.0
    try:
        r = subprocess.run([FFPROBE, "-v", "quiet", "-show_entries",
                            "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True, timeout=30)
        d = float((r.stdout or "0").strip() or 0)
        if d > 0:
            at = max(1.0, d * 0.10)      # 10% in: past the black lead-in, cheap to seek
    except Exception:
        pass
    try:
        r = subprocess.run([FFMPEG, "-y", "-v", "quiet", "-ss", str(at), "-i", src,
                            "-frames:v", "1",
                            "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease",
                            "-q:v", "6", dst], capture_output=True, timeout=120)
        return r.returncode == 0 and os.path.exists(dst)
    except Exception:
        return False


def make(src: str, out_dir: str, size: int) -> tuple[str, str] | None:
    """Returns (hash, thumb_path), or None if it could not be made."""
    ext = os.path.splitext(src)[1].lower()
    if ext not in PHOTO and ext not in VIDEO:
        return None
    try:
        h = content_hash(src)
    except OSError:
        return None
    sub = os.path.join(out_dir, h[:2])
    os.makedirs(sub, exist_ok=True)
    dst = os.path.join(sub, h + ".jpg")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return h, dst                                    # already done: resume
    ok = (_pillow(src, dst, size) or _ffmpeg_image(src, dst, size)) if ext in PHOTO \
        else _ffmpeg_video(src, dst, size)
    return (h, dst) if ok else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="folder tree to thumbnail")
    ap.add_argument("--out", required=True, help="thumbnail cache directory")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="",
                    help="i/n - take only every nth file. Lets several workers "
                         "run without coordinating: the split is by a hash of "
                         "the path, so it is deterministic and disjoint, and no "
                         "two workers ever touch the same file.")
    a = ap.parse_args()

    shard_i = shard_n = 0
    if a.shard:
        shard_i, shard_n = (int(x) for x in a.shard.split("/"))

    os.makedirs(a.out, exist_ok=True)
    made = skipped = failed = 0
    for dp, dns, fns in os.walk(lp(a.source)):
        if "_Catalog" in dp:
            continue
        for fn in fns:
            p = os.path.join(dp, fn).replace("\\\\?\\", "")
            ext = os.path.splitext(fn)[1].lower()
            if ext not in PHOTO and ext not in VIDEO:
                continue
            if shard_n and (zlib.crc32(p.lower().encode()) % shard_n) != shard_i:
                continue
            r = make(p, a.out, a.size)
            if r is None:
                failed += 1
            else:
                made += 1
            if (made + failed) % 500 == 0:
                print(f"  {made:,} thumbs, {failed:,} failed", flush=True)
            if a.limit and made >= a.limit:
                print(f"\nstopped at --limit {a.limit}")
                return
    print(f"\n{made:,} thumbnails, {failed:,} could not be made, cache: {a.out}")
    if failed:
        print("  a failure is a gap in coverage, not a reason to distrust the rest -")
        print("  but check them: a format nothing can open is worth knowing about.")


if __name__ == "__main__":
    main()
