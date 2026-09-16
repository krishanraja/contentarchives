r"""Decide where a file from a source tree belongs: chronology, production, archive.

    python route_h.py "Users\me\Pictures\2019\IMG_0042.jpg"

WHY THIS IS IN THE REPO NOW

It was the one script the publisher refused to publish, and for a good reason
that was also the wrong outcome: its production pattern listed employers,
products and project names literally, so the publication tripwire read its own
routing vocabulary as an identity leak and blocked it on every run. The helper
stayed on the machine, and `ingest_from_h.py` - which imports it - therefore
could not run from the repository at all.

The split, 2026-09-16: the LOGIC is generic and lives here; the identifying
VOCABULARY lives in the profile beside the library and is never committed
(`routing.production_terms`). Without a profile this still routes, using the
generic half alone, and says so rather than pretending the list was empty.

THE ORDER OF THE TESTS IS THE WHOLE DESIGN

Signals are ranked by how self-declaring they are, not by how strong they feel
(learning 29). A file that SAYS what it is beats a pattern somebody recognised:

  0.  self-declared   Screenshot_20230105_031931.png carries the same
                      \d{8}_\d{6} datestamp a camera writes, so the camera test
                      matched first and sent thousands of screenshots into the
                      chronology - the one place Krish did not want them.
  0b. derived copy    a re-encode inherits the camera name of its original, so
                      "DJI_1234_youtube_720p.mp4" reads as provenance. The
                      marker must be a trailing -suffix or _suffix, because that
                      is how an exporter appends to a name it did not choose.
  1.  camera name     positive provenance: DCIM, GH######, IMG_1234, _DSC1215.
  2.  audio           never a chronology entry; it has no visual moment.
  3.  documents       by extension, then by admin path and identity terms.
  4.  produced work   QA, screenshots, node_modules, and the profile's terms.
  5.  not media       archived visibly rather than dropped by the chronology
                      ingest, which only accepts MEDIA_EXT.
  6.  default         media with no work signal is a memory. Permissive ON
                      PURPOSE: a memory misfiled as work is invisible for ever;
                      a work file in the chronology is visible and corrected.

Python's \b treats "_" as a word character, so \bdsc\d{4} does NOT match
"_DSC1215.JPG" (learnings 20, 30). Camera names and flattened paths are made of
underscores, so the boundaries below treat any non-alphanumeric as a separator.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import stagepath  # noqa: E402,F401  - every stage on sys.path, wherever this file lives

from ingest_tree import MEDIA_EXT                                # noqa: E402

B = r"(?<![a-z0-9])"       # left edge
E = r"(?![a-z0-9])"        # right edge

CAMERA = re.compile(
    rf"(dcim|100media|100_|{B}gh\d{{6}}{E}|{B}gx\d{{6}}{E}|{B}gopr\d+|"
    rf"{B}dji_?\d+|{B}img_?\d{{4}}|{B}dsc_?\d{{4}}|{B}p\d{{7}}{E}|"
    rf"{B}vid_?\d{{8}}|{B}pano|{B}mvimg|\d{{8}}_\d{{6}}|"
    rf"{B}signal-\d{{4}}-\d{{2}}-\d{{2}}|photo[-_]\d{{4}}[-_]\d{{2}})", re.I)

# The generic half of "produced, not remembered". The other half - employer,
# product and project names - comes from the profile, because those are the
# terms that identify a person and must not sit in a public repository.
PRODUCTION_GENERIC = [
    r"qa-", r"qa_", rf"-qa{E}", r"uxtest", r"pwtest", r"prerender",
    rf"{B}shots?{E}", r"screenshot", r"screen[-_ ]?record", r"content produced",
    r"content production", r"podcast", rf"{B}evidence{E}", rf"{B}demo{E}",
    r"outreach", r"node_modules", rf"{B}logo{E}", r"favicon", r"wireframe",
    r"mockup",
]

ARCHIVE_PATH = re.compile(
    r"([\\/][^\\/]*_files[\\/]|[\\/](documents|my documents|taxes?|tax returns?|"
    r"music|appdata|program files|windows|temp|cache|downloads?[\\/]_?archive)"
    r"[\\/]|(?<![a-z])(oci|passport|visa|birth cert|citizenship|licence|license|"
    r"aadhaar|pan card|tax return|bank statement|payslip|invoice|receipt|"
    r"medicare|insurance)(?![a-z]))", re.I)

DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
           ".txt", ".rtf", ".odt", ".ods", ".ics", ".eml", ".msg", ".vcf",
           ".json", ".xml", ".html", ".htm", ".md", ".log"}
AUDIO_EXT = {".mp3", ".m4a", ".oga", ".ogg", ".wav", ".aac", ".flac", ".wma",
             ".opus", ".amr"}

CHRONOLOGY, PRODUCTION_D, ARCHIVE = "chronology", "production", "archive"

SELF_DECLARED = re.compile(r"(screen[-_ ]?shot|screen[-_ ]?record|"
                           r"screen[-_ ]?capture|\bscrnshot)", re.I)

DERIVED = re.compile(
    r"[-_](youtube|vimeo|proxy|preview|compressed|converted|transcode[d]?|"
    r"reencode[d]?|re-encode[d]?|export|web|lowres|low-res|"
    r"\d{3,4}p)(?![a-z0-9])", re.I)


def _production_pattern():
    """Generic markers, plus this person's own terms if a profile exists.

    A missing profile is NOT silently an empty list here: it would quietly route
    an employer's QA folder into the chronology and look like success
    (learning 41). It routes on the generic half and says what it is missing.
    """
    terms = list(PRODUCTION_GENERIC)
    try:
        from guards.profile import load
        prof = load(required=False)
    except Exception:                                            # noqa: BLE001
        prof = None
    if prof and prof.production_terms:
        terms += [re.escape(t) for t in prof.production_terms]
    else:
        print("route_h: no profile terms - routing on generic markers only. "
              "Employer and project folders will read as memories.", file=sys.stderr)
    return re.compile("(" + "|".join(terms) + ")", re.I)


PRODUCTION = _production_pattern()


def route(rel_path: str) -> tuple[str, str]:
    """Return (destination, the signal that decided it).

    `rel_path` is relative to the source root, so the folder structure the
    person built is part of the evidence.
    """
    ext = os.path.splitext(rel_path)[1].lower()

    m = SELF_DECLARED.search(rel_path)
    if m:
        return PRODUCTION_D, f"self-declared '{m.group(0)}'"

    m = DERIVED.search(os.path.basename(rel_path))
    if m and ext in MEDIA_EXT:
        return PRODUCTION_D, f"derived-copy marker '{m.group(0)}'"

    m = CAMERA.search(rel_path)
    if m and ext not in DOC_EXT and ext not in AUDIO_EXT:
        return CHRONOLOGY, f"camera name '{m.group(0)}'"

    if ext in AUDIO_EXT:
        return ARCHIVE, f"audio {ext}"

    if ext in DOC_EXT:
        return ARCHIVE, f"document {ext}"

    m = ARCHIVE_PATH.search("\\" + rel_path)
    if m:
        return ARCHIVE, f"admin path '{m.group(0).strip(chr(92))[:28]}'"

    m = PRODUCTION.search(rel_path)
    if m:
        return PRODUCTION_D, f"production marker '{m.group(0)}'"

    if ext not in MEDIA_EXT:
        return ARCHIVE, f"not media ({ext or 'no extension'})"

    return CHRONOLOGY, "default: media with no work signal"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        d, why = route(arg)
        print(f"{d:<11} {why:<34} {arg}")
