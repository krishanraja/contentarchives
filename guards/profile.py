r"""The personal half of the configuration, kept OUT of this repository.

    from guards.profile import load
    p = load()
    if p.is_personal(path): ...
    for term in p.personal_terms: ...

WHY THIS EXISTS

This repository is public. Until 2026-09-16 the working scripts lived on the
machine and were published through a redaction pass: family names, an employer,
a username all rewritten to pseudonyms. That kept the repo clean and made the
published copy USELESS - 34 executable lines carried a pseudonym, so the version
anybody could read was a version nobody could run, and the machine kept the only
runnable one. Two codebases, one of them on a disk that logs controller errors.

The fix is not better redaction. It is that code holds no personal detail at
all: machine paths in guards/paths.py, and everything about particular PEOPLE in
a profile file that lives beside the library and is never committed.

    %USERPROFILE%\.contentarchives\profile.yaml     (default)
    CONTENTARCHIVES_PROFILE=<path>                  (override)
    profiles/example.yaml                           the shape, with no real terms

WHAT IT IS FOR, AND WHAT IT IS NOT FOR

Terms here mark material as personal, which OVERRIDES every exclusion rule: a
path containing a family name is never swept, never compressed, never deleted
(learning 1). They are not a classifier. A term is grounds to KEEP and to ask a
human; it is never grounds to delete.

A missing profile is not an empty one. Nothing here silently returns "no
personal terms" - that would turn every protection into a no-op and report
success (learnings 34, 41). Callers that can work without it ask for
load(required=False) and get None, which they must handle out loud.
"""

from __future__ import annotations

import io
import os

DEFAULT = os.path.join(os.path.expanduser("~"), ".contentarchives", "profile.yaml")
ENV = "CONTENTARCHIVES_PROFILE"


class Profile:
    def __init__(self, data: dict, path: str):
        self.path = path
        self._d = data or {}
        self.name = self._d.get("name") or "unnamed"
        safety = self._d.get("safety") or {}
        self.personal_terms = [str(t).lower() for t in (safety.get("personal_terms") or [])]
        self.review_hints = [str(t).lower() for t in (safety.get("review_hints") or [])]
        self.likely_disposable = list(safety.get("likely_disposable") or [])
        self.confirm_deletions = bool(safety.get("confirm_deletions", True))

    def is_personal(self, text: str) -> bool:
        """True if this path or name carries a term that means "this matters".

        Substring, deliberately: a filename separates words with underscores,
        hyphens and digits, and \\b treats underscore as a letter, so a word
        boundary misses `_CommBank` and half of what it is asked to catch
        (learnings 20, 30). A false positive here costs a review; a false
        negative costs a photograph.
        """
        t = (text or "").lower()
        return any(term and term in t for term in self.personal_terms)

    def needs_review(self, text: str) -> bool:
        t = (text or "").lower()
        return any(term and term in t for term in self.review_hints)

    def __repr__(self) -> str:
        return "<Profile {!r} from {} - {} personal terms>".format(
            self.name, self.path, len(self.personal_terms))


def path_of() -> str:
    return os.environ.get(ENV) or DEFAULT


def load(required: bool = True) -> Profile | None:
    """The profile, or STOP. required=False returns None for optional callers."""
    p = path_of()
    if not os.path.isfile(p):
        if not required:
            return None
        raise SystemExit(
            "STOPPING: no profile at {}\n"
            "  It holds the terms that mark YOUR material as personal, and they\n"
            "  are deliberately not in this repository. Copy profiles/example.yaml\n"
            "  there and fill it in, or set {}=<path>.\n"
            "  Running without it would treat every protective term as absent and\n"
            "  report success (learning 41).".format(p, ENV))
    text = io.open(p, encoding="utf-8").read()
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "STOPPING: PyYAML is not installed, so {} cannot be read.\n"
            "  pip install pyyaml - it is in requirements.txt".format(p))
    data = yaml.safe_load(text) or {}
    prof = Profile(data, p)
    if required and not prof.personal_terms:
        raise SystemExit(
            "STOPPING: {} lists no safety.personal_terms.\n"
            "  An empty list and a missing file look the same to every caller,\n"
            "  and both disable the rule that protects your own material.\n"
            "  Add the names, places and trips whose presence means 'this matters'."
            .format(p))
    return prof
