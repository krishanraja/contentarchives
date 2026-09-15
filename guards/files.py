"""Reading and writing files without the failures this project has already paid for.

    with atomic_writer(path) as f:        # a reader sees the old file or the new one
        f.write(...)

    require_dir(path, "frames")           # an absent input stops, it is not "empty"
    for line in complete_lines(f): ...    # never the half-written last line
"""

from __future__ import annotations

import io
import os
from contextlib import contextmanager


@contextmanager
def atomic_writer(path: str, mode: str = "w", encoding: str = "utf-8",
                  newline: str | None = ""):
    """Write to <path>.tmp, fsync, then rename over <path>.

    Learning 42: INVENTORY.csv read as 572 rows of an 82,635-row file because it
    was being rewritten in place at that moment. A rename is atomic, so a reader
    gets the previous version or this one and never a prefix. If the body
    raises, the temporary file is removed and the previous version is untouched.
    """
    tmp = path + ".tmp"
    binary = "b" in mode
    f = io.open(tmp, mode) if binary else io.open(tmp, mode, encoding=encoding,
                                                  newline=newline)
    try:
        yield f
        f.flush()
        os.fsync(f.fileno())
    except BaseException:
        f.close()
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    f.close()
    os.replace(tmp, path)


def atomic_write_text(path: str, text: str) -> None:
    with atomic_writer(path) as f:
        f.write(text)


def require_dir(path: str, what: str = "directory") -> str:
    """Return path if it is a directory; otherwise STOP.

    Learning 34: os.walk on a directory that does not exist yields nothing, so a
    646 GB library was reported as 0 files for two days. An absent input is not
    an empty one.
    """
    if not os.path.isdir(path):
        raise SystemExit("STOPPING: {} not found at {} - an absent input is not an "
                         "empty one (learning 34)".format(what, path))
    return path


def require_file(path: str, what: str = "file") -> str:
    """Return path if it is a file; otherwise STOP (learnings 34, 41)."""
    if not os.path.isfile(path):
        raise SystemExit("STOPPING: {} not found at {} - a missing input must not "
                         "read as nothing to report (learning 41)".format(what, path))
    return path


def complete_lines(f):
    """Yield the lines of f, leaving out a final line with no newline.

    Learning 42: a producer appending to a file flushes at arbitrary byte
    offsets, so its last line is often half a row. Half an embedding decodes
    wrong and reads as corruption; a verifier that believes it kills a healthy
    run. The unfinished line is still being written - leave it for next time.
    """
    prev = None
    for line in f:
        if prev is not None:
            yield prev
        prev = line
    if prev is not None and prev.endswith("\n"):
        yield prev
