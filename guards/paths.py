r"""Every path the toolkit uses, in one place.

Before this file, `D:\PhotoLibrary` was hardcoded in 40 of 77 scripts, 85 times.
Renaming the library therefore meant 85 edits, and the failure mode of missing
one is not an error - it is a script quietly reading or writing a path that no
longer exists. That is exactly how the dedup index came to cover 12% of the
library while reporting success, and how 207 GB of duplicates were admitted
without a single exception being raised.

So: one definition, imported. A rename becomes one edit here.

THE LAYOUT, AND WHY IT IS SHAPED THIS WAY

    D:\ContentLibrary\
    |-- Media\                    everything with a date, in a chronology
    |   |-- Personal\YYYY\YYYY-MM\
    |   |-- Communal\YYYY\YYYY-MM\
    |   |-- NoDate\
    |   `-- Pending-Segmentation\ ingested, not yet assigned a side
    |-- Archive\                  documents and admin: identity, financial, work
    |-- ContentProduction\        podcasts, exports, produced work
    |-- _Review\                  judged not-a-memory. NOT deleted. A human empties it.
    `-- _Catalog\                 the manifest

A `YYYY\YYYY-MM\` tree is right for a life and wrong for everything else, which
is why documents and produced content sit BESIDE `Media\` rather than inside it.
`ContentLibrary` is one root, so the mirror to H: has one root too.

`Pending-Segmentation` is hyphenated on purpose: a space survives Python and CSV
perfectly well and then breaks the first unquoted shell command that meets it.
"""

from __future__ import annotations

import os

ROOT = r"D:\ContentLibrary"

MEDIA = os.path.join(ROOT, "Media")
PERSONAL = os.path.join(MEDIA, "Personal")
COMMUNAL = os.path.join(MEDIA, "Communal")
NODATE = os.path.join(MEDIA, "NoDate")
PENDING = os.path.join(MEDIA, "Pending-Segmentation")

ARCHIVE = os.path.join(ROOT, "Archive")
PRODUCTION = os.path.join(ROOT, "ContentProduction")
REVIEW = os.path.join(ROOT, "_Review")
CATALOG = os.path.join(ROOT, "_Catalog")
MANIFEST = os.path.join(CATALOG, "manifest.csv")

AUDIT = r"D:\_PhotoAudit"
SCRIPTS = os.path.join(AUDIT, "scripts")
TMPDIR = r"D:\_takeout_tmp"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Scratch trees this project creates and is allowed to empty, once each has been
# PROVEN to hold nothing unique. None of them may sit inside ROOT: clearing a
# scratch dir nested in the library would delete library content.
SCRATCH_DIRS = [
    TMPDIR,
    r"D:\_h_stage",
    r"D:\_h_speedtest",
    r"D:\_stage",
    r"D:\_tmp",
]

# Where new material arrives. Five scripts each kept their own copy of this list
# with a hardcoded username in it; one definition means a new source is one edit.
SOURCES = [
    os.path.join(os.path.expanduser("~"), "Downloads"),
    r"D:\\",
    r"D:\Takeout",
    r"C:\GoogleTakeout",
]
WATCH_DIRS = list(SOURCES)

# Folders that are this project's own bookkeeping, never ingested as media.
SKIP_FOLDERS = {"_audit-trail", "in", "out"}

# Google Drive for Desktop's own state, under the CURRENT user. Its `operations`
# table is the only honest answer to "has this really uploaded?" - the mount
# itself serves the local cache and will happily verify bytes against themselves
# (learning 25).
DRIVEFS = os.path.join(os.environ.get("LOCALAPPDATA")
                       or os.path.join(os.path.expanduser("~"), "AppData", "Local"),
                       "Google", "DriveFS")


def _resolve(binary: str, required: bool = True) -> str | None:
    """Find an external tool. Raise when it is missing; never return "".

    Learning 41: FFPROBE was hardcoded to one machine's username, probe_video()
    returned an empty dict when the binary was absent, and a 33-minute pass wrote
    no duration for any of 12,988 videos while reporting success. A missing
    dependency must be loud, and a falsy return value is not loud.

    Order: an explicit override, then PATH, then a glob under the CURRENT user's
    WinGet packages - never another machine's profile.
    """
    import glob
    import shutil

    env = os.environ.get(binary.upper().replace("-", "_") + "_PATH")
    if env and os.path.exists(env):
        return env
    found = shutil.which(binary)
    if found:
        return found
    pattern = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft",
                           "WinGet", "Packages", "*", "**", binary + ".exe")
    for hit in glob.glob(pattern, recursive=True):
        return hit
    if required:
        raise SystemExit(
            "STOPPING: {0} was not found.\n"
            "  Looked at ${1}_PATH, then PATH, then this user's WinGet packages.\n"
            "  Install it or set the variable - a missing tool that returns an\n"
            "  empty result writes an empty column and calls it success "
            "(learning 41).".format(binary, binary.upper()))
    return None


def ffprobe(required: bool = True) -> str | None:
    return _resolve("ffprobe", required)


def ffmpeg(required: bool = True) -> str | None:
    return _resolve("ffmpeg", required)

# Every root the dedup index must cover. Anything holding library content and
# missing from this list is invisible to deduplication - the bug that cost
# 21,649 duplicate files. _Review is included deliberately: a file judged
# not-a-memory should be recognised on re-import, not quietly reinstated.
INDEX_ROOTS = [PENDING, NODATE, PERSONAL, COMMUNAL, REVIEW]

# Everything the inventory describes. Narrower coverage than this silently
# reports real files as unknown - 33 files in Archive\ appeared that way.
INVENTORY_ROOTS = [ROOT]

# The chronology, in the sense of "has a date and belongs to a life".
CHRONOLOGY = [PERSONAL, COMMUNAL, NODATE, PENDING]

# --- the migration this file records -------------------------------------
# Old -> new, longest first so the more specific rule wins. Used to rewrite the
# manifest, inventory, origin map and journals in step with the moves.
PATH_MIGRATION = [
    (r"D:\PhotoLibrary\Library",   PENDING),
    (r"D:\PhotoLibrary\Personal",  PERSONAL),
    (r"D:\PhotoLibrary\Communal",  COMMUNAL),
    (r"D:\PhotoLibrary\NoDate",    NODATE),
    (r"D:\PhotoLibrary\_Review",   REVIEW),
    (r"D:\PhotoLibrary\_Catalog",  CATALOG),
    (r"D:\PhotoLibrary",           ROOT),
    (r"D:\ContentProduction",      PRODUCTION),
    (r"D:\Archive",                ARCHIVE),
]


def migrate(path: str) -> str:
    """Rewrite one old path to its new home. Unrecognised paths pass through
    untouched - an origin on C:, G: or inside a consumed archive is not ours
    to rewrite."""
    for old, new in PATH_MIGRATION:
        if path.lower().startswith(old.lower()):
            return new + path[len(old):]
    return path


# Relative library paths, as ORIGIN-MAP.csv stores them (107,234 of its 109,207
# rows). They are relative to the OLD root, so they carry the pre-migration tree
# names and need the same mapping applied before they mean anything.
RELATIVE_MIGRATION = [
    ("Library",  os.path.join("Media", "Pending-Segmentation")),
    ("Personal", os.path.join("Media", "Personal")),
    ("Communal", os.path.join("Media", "Communal")),
    ("NoDate",   os.path.join("Media", "NoDate")),
]


def resolve(p: str) -> str:
    """Any recorded library path -> where that file lives now.

    Handles absolute paths, and the relative ones the origin map uses. A record
    that silently fails to resolve reads as 'this file does not exist', which is
    how a selector returned zero rows for 13,368 files that were all present.
    """
    if not p:
        return p
    if p[1:2] == ":":
        return migrate(p)
    head = p.split(os.sep)[0]
    for old, new in RELATIVE_MIGRATION:
        if head.lower() == old.lower():
            return os.path.join(ROOT, new + p[len(old):])
    return os.path.join(ROOT, p)
