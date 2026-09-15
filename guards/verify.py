"""The one exit-code contract every verifier in this repo speaks.

    0  OK           a sample was re-derived from its source and all of it matched
    1  WRONG        something re-derived differently - or nothing COULD be
    2  CANNOT_TELL  there is nothing to check yet (no output written)

Chains accept 2 while work is starting and demand 0 at the end.

The rule this encodes is learning 6's fallback branch: a check with no failure
mode is not a check. "Sampled five, re-derived none" used to return 2, which the
chain accepts, so a verifier that could no longer load its model or find its
images would have passed for ever. It is WRONG.

And learning 46: a verifier RE-DERIVES the answer and compares. It never
inspects the output's shape - on the corrupt face file every row was well-formed.
"""

from __future__ import annotations

OK, WRONG, CANNOT_TELL = 0, 1, 2


def verdict(sampled: int, checked: int, wrong: int) -> int:
    """sampled: items picked to check; checked: re-derived; wrong: mismatched."""
    if wrong:
        return WRONG
    if sampled == 0:
        return CANNOT_TELL
    if checked == 0:
        return WRONG
    return OK
