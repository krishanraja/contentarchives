r"""Put every stage, guards/ and the package root on sys.path. Import me first.

    import stagepath                      # from a stage script
    stagepath.script("build_db.py")       # -> the path it lives at now

WHY

Before the conveyor, each script reached its neighbours with its own path hack:

    sys.path.insert(0, os.path.join(HERE, "..", "stages", "05_enrich"))

which encodes the depth of the file that wrote it. Moving that file one directory
deeper silently resolves to a directory that does not exist, and the import fails
at run time rather than at review time - or worse, finds a stale copy. There were
also two absolute paths under a username from a different machine.

So: one definition of where things are. A stage script needs two lines, and they
do not care where the file sits:

    sys.path.insert(0, <repo root>)       # found by walking up to stagepath.py
    import stagepath                      # noqa: F401  - extends sys.path

Directories are asserted to exist, because an absent input is not an empty one
(learning 34): a mistyped stage name fails here, loudly, and not as a puzzling
ImportError three files away.

script() exists because some steps launch others as subprocesses (refresh.py runs
track.py, a chain runs build_db.py). A name resolves to wherever the conveyor
keeps that file now, so a move does not have to be chased through every caller.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Every directory that holds importable modules, in the order a stage should see
# them: its own neighbours first, then the shared ones.
_DIRS = ["guards", "contentarchives"]
_STAGES = os.path.join(ROOT, "stages")
if os.path.isdir(_STAGES):
    _DIRS += [os.path.join("stages", d) for d in sorted(os.listdir(_STAGES))
              if os.path.isdir(os.path.join(_STAGES, d))]
# still-unmoved trees, dropped from this list as each stage moves
_DIRS += ["tools", "scripts"]


def _add(rel: str) -> str | None:
    p = os.path.join(ROOT, rel)
    if not os.path.isdir(p):
        return None
    if p not in sys.path:
        sys.path.insert(0, p)
    return p


_ADDED = [p for p in (_add(d) for d in _DIRS) if p]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def dirs() -> list[str]:
    """Every directory this put on sys.path, nearest first."""
    return list(_ADDED)


def script(name: str) -> str:
    """Where a named script lives now. Raises rather than returning a guess.

    A caller that launches `python <path>` must not be handed a path that does
    not exist - a subprocess failing with "can't open file" three hours into a
    chain is the expensive way to learn a file moved.
    """
    for d in _ADDED:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise SystemExit(
        "STOPPING: no script called {} in any stage. Looked in:\n  {}".format(
            name, "\n  ".join(_ADDED)))


def find(name: str) -> str | None:
    """script(), but None instead of stopping - for optional inputs."""
    try:
        return script(name)
    except SystemExit:
        return None
