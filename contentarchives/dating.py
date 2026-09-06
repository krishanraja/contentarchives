"""Work out when a photo or video was actually taken.

Filesystem mtime is worthless in a synced archive - sync clients, backup tools and
cloud downloads all rewrite it. See docs/LEARNINGS.md rule 3. In one real corpus
40.6% of files had no trustworthy date from the filesystem.

Precedence, best first:
    filename pattern  ->  EXIF DateTimeOriginal  ->  container metadata
    ->  sidecar JSON  ->  enclosing folder name  ->  give up

"Give up" means NoDate, not mtime. An invented date is worse than an absent one,
because it silently files a 2018 photo under 2026 and nobody ever notices.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DateResult", "date_for", "MIN_YEAR"]

MIN_YEAR = 1990

# yyyymmdd_hhmmss, yyyy-mm-dd, bare yyyymmdd - in that order of confidence
_PATTERNS = (
    re.compile(r"(?<!\d)(19|20)(\d{2})(\d{2})(\d{2})[_\-]?(\d{2})(\d{2})(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(19|20)(\d{2})[-_.](\d{2})[-_.](\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(19|20)(\d{2})(\d{2})(\d{2})(?!\d)"),
)

_JPEG_EXT = {".jpg", ".jpeg"}
_VIDEO_EXT = {".mp4", ".mov", ".avi", ".m2ts", ".3gp", ".mkv", ".wmv",
              ".m4v", ".mpg", ".mpeg", ".webm"}


@dataclass(frozen=True)
class DateResult:
    year: str | None
    month: str | None
    source: str          # filename | exif | container | sidecar | folder | none

    @property
    def known(self) -> bool:
        return self.year is not None

    def bucket(self) -> str:
        """Where this file should be filed."""
        return f"{self.year}/{self.year}-{self.month}" if self.known else "NoDate"


def _plausible(y: int, mo: int, d: int) -> bool:
    return MIN_YEAR <= y <= _dt.date.today().year and 1 <= mo <= 12 and 1 <= d <= 31


def _from_text(text: str) -> tuple[str, str] | None:
    """Pull a date out of a filename or folder name."""
    for rx in _PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        y = int(m.group(1) + m.group(2))
        mo, d = int(m.group(3)), int(m.group(4))
        if _plausible(y, mo, d):
            return f"{y:04d}", f"{mo:02d}"
    return None


def _from_exif(path: Path) -> tuple[str, str] | None:
    """Parse EXIF DateTimeOriginal straight out of the JPEG APP1 segment.

    Deliberately dependency-free and header-only: reads at most 128 KB, which
    matters when the file may be a cloud placeholder that hydrates on access.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(131072)
    except OSError:
        return None
    if head[:2] != b"\xff\xd8":
        return None

    i = 2
    while i < len(head) - 4:
        if head[i] != 0xFF:
            i += 1
            continue
        marker = head[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:          # start of scan - no EXIF beyond here
            break
        try:
            seglen = struct.unpack(">H", head[i + 2:i + 4])[0]
        except struct.error:
            break
        seg = head[i + 4:i + 2 + seglen]
        if marker == 0xE1 and seg[:6] == b"Exif\x00\x00":
            return _read_tiff(seg[6:])
        i += 2 + seglen
    return None


def _read_tiff(tiff: bytes) -> tuple[str, str] | None:
    try:
        endian = "<" if tiff[:2] == b"II" else ">" if tiff[:2] == b"MM" else None
        if endian is None:
            return None
        offset = struct.unpack(endian + "I", tiff[4:8])[0]
        for _ in range(3):          # IFD0, then the Exif sub-IFD
            if offset <= 0 or offset + 2 > len(tiff):
                return None
            count = struct.unpack(endian + "H", tiff[offset:offset + 2])[0]
            exif_ptr = None
            for k in range(count):
                e = offset + 2 + k * 12
                if e + 12 > len(tiff):
                    break
                tag, typ, cnt = struct.unpack(endian + "HHI", tiff[e:e + 8])
                val = struct.unpack(endian + "I", tiff[e + 8:e + 12])[0]
                if tag in (0x9003, 0x0132) and typ == 2 and cnt >= 19:
                    s = tiff[val:val + 19].decode("ascii", "ignore")
                    m = re.match(r"(\d{4}):(\d{2}):(\d{2})", s)
                    if m and _plausible(int(m.group(1)), int(m.group(2)), int(m.group(3))):
                        return m.group(1), m.group(2)
                elif tag == 0x8769:
                    exif_ptr = val
            if exif_ptr is None:
                return None
            offset = exif_ptr
    except Exception:
        return None
    return None


def _from_container(path: Path, ffprobe: str | None) -> tuple[str, str] | None:
    """Video container creation_time, via ffprobe. Header read only."""
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_entries", "format_tags=creation_time", str(path)],
            capture_output=True, text=True, timeout=60,
        ).stdout
        ts = (json.loads(out or "{}").get("format", {}).get("tags", {}) or {}).get("creation_time")
        if not ts:
            return None
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", ts)
        if m and _plausible(int(m.group(1)), int(m.group(2)), int(m.group(3))):
            return m.group(1), m.group(2)
    except Exception:
        return None
    return None


def _from_sidecar(path: Path) -> tuple[str, str] | None:
    """Google Takeout ships photoTakenTime next to each file."""
    for cand in (path.with_suffix(path.suffix + ".json"),
                 path.with_suffix(path.suffix + ".supplemental-metadata.json")):
        if not cand.exists():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8", errors="ignore"))
            ts = (data.get("photoTakenTime") or {}).get("timestamp")
            if ts:
                d = _dt.datetime.fromtimestamp(int(ts), _dt.timezone.utc)
                if _plausible(d.year, d.month, d.day):
                    return f"{d.year:04d}", f"{d.month:02d}"
        except Exception:
            continue
    return None


def date_for(
    path: str | os.PathLike,
    *,
    ffprobe: str | None = None,
    sidecar_dates: dict[str, str] | None = None,
) -> DateResult:
    """Best available capture date, with its provenance.

    ``sidecar_dates`` lets an archive reader pass in timestamps harvested from
    JSON members it has already streamed past, keyed by lowercase filename.
    """
    p = Path(path)
    ext = p.suffix.lower()

    hit = _from_text(p.name)
    if hit:
        return DateResult(hit[0], hit[1], "filename")

    if ext in _JPEG_EXT:
        hit = _from_exif(p)
        if hit:
            return DateResult(hit[0], hit[1], "exif")

    if ext in _VIDEO_EXT:
        hit = _from_container(p, ffprobe)
        if hit:
            return DateResult(hit[0], hit[1], "container")

    if sidecar_dates:
        ts = sidecar_dates.get(p.name.lower())
        if ts:
            try:
                d = _dt.datetime.fromtimestamp(int(ts), _dt.timezone.utc)
                if _plausible(d.year, d.month, d.day):
                    return DateResult(f"{d.year:04d}", f"{d.month:02d}", "sidecar")
            except Exception:
                pass
    else:
        hit = _from_sidecar(p)
        if hit:
            return DateResult(hit[0], hit[1], "sidecar")

    hit = _from_text(str(p.parent))
    if hit:
        return DateResult(hit[0], hit[1], "folder")

    # Deliberately NOT falling back to mtime.
    return DateResult(None, None, "none")
