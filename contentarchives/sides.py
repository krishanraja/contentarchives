r"""Whose life is this photograph from? One answer, in one place.

    from sides import side_of, is_majority_communal
    side_of(r"D:\ContentLibrary\Media\Personal\2019\a.jpg")   -> "Personal"
    side_of(r"D:\ContentLibrary\Archive\Communal\01-Identity\b.jpg") -> "Communal"

WHY IT IS NOT files.side

`files.side` holds the TOP-LEVEL TREE - `Media`, `Archive`, `_Review`,
`ContentProduction`. Joining on it to find Personal photographs returned zero of
58,033 and would have excluded Krish's entire remaining naming queue. Personal
and Communal live one level DOWN. The side comes from the path, always.

WHY IT IS IN ONE FILE NOW

There were two copies: `stages/07_people/people_sheet.py` and
`stages/06_faces/../name_clusters.py` each defined their own `side_of`. Two
copies of a rule drift - that is how five near-identical profile scripts
accumulated across rounds 13-15, and how `check_repeats.py` carried a stale
`PEOPLE-round[1-6]` pattern for three rounds while calling every sheet clean. A
rule that decides whose photographs a human is asked about should exist once.

WHY IT READS MORE THAN Media

`Archive\Personal`, `Archive\Communal`, `_Review\Personal` and
`_Review\Communal` state a side in their own path - somebody put them there
deliberately. Reading only `\Media\...` left **1,230 files unsided** that were
already sided, and they were about to be dragged across a disk to fix a function
instead. Measured 2026-09-18: Archive\Personal 1,013, _Review\Personal 166,
_Review\Communal 34, Archive\Communal 17.

`Media\Pending-Segmentation` and `Media\NoDate` are NOT sides. They are the
queue, and they answer with their own name - `"Pending"` and `"NoDate"` - which
is what makes them findable. An early version of this file flattened both to
`"other"`; those strings are load-bearing in `tools/track.py`,
`tools/audit_split.py`, `tools/audit_previous_session.py`,
`stages/11_mirror/postswap_check.py` and `stages/09_segment/apply_split.py`, and
the test that caught it was right to object.
"""

from __future__ import annotations

import re

# One level under any tree that states a side. Anchored on separators so
# `\Media\PersonalStuff\` never reads as Personal.
_SIDED = re.compile(r"\\(?:media|archive|_review)\\(personal|communal)\\", re.I)
# The queues. Not sides - but they name themselves, because the rest of the
# project asks "how much is still in NoDate?" and needs an answer.
_QUEUE = ((r"\media\nodate\\", "NoDate"),
          (r"\media\pending-segmentation\\", "Pending"))


def side_of(path: str | None) -> str:
    """"Personal", "Communal", "NoDate", "Pending", or "other".

    Never None and never a guess. A queue name is a real answer: that material
    genuinely has no side yet, and a caller that treats it as Personal is making
    a decision it should make out loud.
    """
    p = (path or "").replace("/", "\\")
    m = _SIDED.search(p)
    if m:
        return "Personal" if m.group(1).lower() == "personal" else "Communal"
    low = p.lower()
    for needle, name in _QUEUE:
        if needle.replace("\\\\", "\\") in low:
            return name
    return "other"


def is_majority_communal(hashes, sides: dict) -> bool:
    """Is this cluster mostly somebody else's? Communal outnumbering Personal.

    A CLUSTER has no side - its photographs do. Krish, 2026-09-17: "Do not make
    me identify any more faces from Communal any more." So the test is a
    comparison within the cluster, and a tie goes to Krish: being asked about a
    photograph of his own is a small cost, and never being asked is a large one.

    `sides` maps hash -> side (as `people_sheet.main()` builds it) or hash ->
    path; either works. Anything that is neither Personal nor Communal -
    NoDate, Pending, other, or a hash nobody knows - counts as neither, which is
    why unsided material stays in Krish's sheets: he was offered the wider
    exclusion on 2026-09-17 and chose true Communal only.
    """
    known = ("Personal", "Communal", "NoDate", "Pending", "other")
    communal = personal = 0
    for h in hashes or ():
        v = sides.get(h)
        s = v if v in known else side_of(v)
        if s == "Communal":
            communal += 1
        elif s == "Personal":
            personal += 1
    return communal > personal
