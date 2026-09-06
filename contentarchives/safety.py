"""Deletion guard.

This module exists because a path-substring rule once permanently destroyed 45
irreplaceable personal files. See docs/LEARNINGS.md rule 1.

The design principle: nothing in this toolkit may decide a deletion from what a
path *looks like*. Deletion is allowlist-only, and every allowed reason is a
narrow, explicit case that a human has reasoned about.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

__all__ = ["DeletionRefused", "Guard", "CAMERA_NAME_RE", "looks_camera_original"]


class DeletionRefused(RuntimeError):
    """Raised whenever a deletion is not explicitly permitted. Never catch this
    to 'try something else' - it means the caller's reasoning was wrong."""


# Filenames produced by cameras and phones. A file matching this is treated as
# irreplaceable regardless of where it sits or what any other rule says.
CAMERA_NAME_RE = re.compile(
    r"^("
    r"IMG[-_]\d|DSC[_NF]?\d|PXL_\d|GOPR\d|GH\d{2}\d|GX\d{2}\d|DJI[-_]\d|"
    r"MVI[-_]\d|MOV_\d|VID[-_]\d|P\d{7}|\d{8}[-_]\d{6}|"
    r"WhatsApp\s+(Image|Video)|Screenshot[-_]\d{8}"
    r")",
    re.IGNORECASE,
)

# Path components that indicate camera-original material wherever they appear.
CAMERA_DIRS = {"dcim", "camera", "camera roll", "100media", "100andro", "100apple"}


def looks_camera_original(path: str | os.PathLike) -> bool:
    """True if this looks like camera-original media.

    Deliberately generous. A false positive costs a file being kept; a false
    negative costs a file being destroyed. Those are not symmetric.
    """
    p = Path(path)
    if CAMERA_NAME_RE.match(p.name):
        return True
    return any(part.lower() in CAMERA_DIRS for part in p.parts)


class Guard:
    """The only sanctioned route to deleting anything.

    Every deletion must name a *reason*, and each reason has narrow rules:

    ``scratch``
        A temporary file this tool created, inside ``scratch_dir``.

    ``verified-duplicate``
        The identical bytes are proven to exist elsewhere. The caller must pass
        ``proof`` - the path whose whole-file hash matched. Refused for anything
        that looks camera-original unless ``allow_camera_originals`` is set on
        the Guard, which callers should not do casually.

    ``consumed-archive``
        An archive whose every member has been accounted for. The caller must
        pass ``accounted=True``.

    Anything inside a protected root is refused unconditionally, whatever the
    reason. Protected roots are the library itself and any source directory.
    """

    def __init__(
        self,
        scratch_dir: str | os.PathLike,
        protected_roots: Iterable[str | os.PathLike] = (),
        allow_camera_originals: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.scratch = Path(scratch_dir).resolve()
        self.protected = [Path(p).resolve() for p in protected_roots]
        self.allow_camera_originals = allow_camera_originals
        self.dry_run = dry_run
        self.deleted: list[tuple[str, str]] = []

        # Structural precondition: if scratch lived inside a protected root, the
        # scratch allowlist would be a hole straight through the guard.
        for root in self.protected:
            if _is_within(self.scratch, root):
                raise DeletionRefused(
                    f"scratch dir {self.scratch} is inside protected root {root}"
                )

    # ------------------------------------------------------------------ public

    def remove(
        self,
        path: str | os.PathLike,
        reason: str,
        *,
        proof: str | os.PathLike | None = None,
        accounted: bool = False,
    ) -> None:
        target = Path(path).resolve()

        for root in self.protected:
            if _is_within(target, root):
                raise DeletionRefused(f"refused: {target} is inside protected root {root}")

        if reason == "scratch":
            if not _is_within(target, self.scratch):
                raise DeletionRefused(f"refused: {target} is not in scratch ({self.scratch})")

        elif reason == "verified-duplicate":
            if proof is None:
                raise DeletionRefused(f"refused: {target} - no proof path supplied")
            if not Path(proof).exists():
                raise DeletionRefused(f"refused: {target} - proof {proof} does not exist")
            if looks_camera_original(target) and not self.allow_camera_originals:
                raise DeletionRefused(
                    f"refused: {target} looks camera-original; "
                    "set allow_camera_originals explicitly if you truly mean it"
                )

        elif reason == "consumed-archive":
            if not accounted:
                raise DeletionRefused(f"refused: {target} - members not fully accounted for")

        else:
            raise DeletionRefused(f"refused: {target} - unknown reason {reason!r}")

        self.deleted.append((str(target), reason))
        if not self.dry_run:
            os.remove(_long(target))

    # ---------------------------------------------------------------- internal

    def would_refuse(self, path, reason, **kw) -> str | None:
        """Test a deletion without performing it. Returns the refusal message,
        or None if it would be permitted. Useful in tests and dry runs."""
        saved, self.dry_run = self.dry_run, True
        try:
            self.remove(path, reason, **kw)
            return None
        except DeletionRefused as exc:
            return str(exc)
        finally:
            self.dry_run = saved


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _long(p: Path) -> str:
    """Windows MAX_PATH escape. Harmless elsewhere."""
    s = str(p)
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s
