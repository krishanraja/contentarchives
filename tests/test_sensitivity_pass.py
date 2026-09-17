r"""The nudity pass must never write `sensitivity`. Hold it to that in code.

    python tests\test_sensitivity_pass.py

WHY THIS TEST EXISTS

`classify_live.py --sensitivity` asks one narrow question - is anyone unclothed -
of two populations the main classification pass cannot answer for: files it never
saw, and the 737 files in the `private-family` middle tier.

The answer decides whether a photograph gets moved into Personal\Intimate. That
makes this the single most consequential field in the store, and the rule is:

    a model may propose; only a human may write `sensitivity`.

If the pass ever wrote `sensitivity` itself, its guess would enter the same
field the sweep acts on, and files would relocate on a model's say-so - with no
way afterwards to tell which moves a person had actually agreed to. store.py's
provenance rule exists for exactly this, and 88 files were already moved once on
labels nobody re-checked.

That rule currently lives in a comment I wrote. A comment is not enforcement:
this stage's STAGE.md said "Tests: none yet (debt)" while carrying the
classifier, which is how `sensitivity` came to be trusted at 0.1% without anyone
measuring recall. So the invariant goes here, where a future edit that breaks it
fails the build instead of quietly refiling someone's photographs.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
import stagepath  # noqa: E402,F401
sys.path.insert(0, os.path.join(REPO, "stages", "05_enrich"))

import classify_live as C                                         # noqa: E402

FAILURES = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("  {:<64} {}".format(name, "ok" if ok else "FAIL"))
    if not ok:
        FAILURES.append("{}{}".format(name, "  -  " + detail if detail else ""))


print("1. the pass proposes; it never writes the field that moves files")
check("`sensitivity` is not among the fields it writes",
      "sensitivity" not in C.SENS_FIELDS,
      "SENS_FIELDS = {}".format(C.SENS_FIELDS))
check("nor is any other field the main pass owns",
      not (set(C.SENS_FIELDS) & set(C.FIELDS)),
      "overlap: {}".format(sorted(set(C.SENS_FIELDS) & set(C.FIELDS))))
check("nor any field the rich pass owns",
      not (set(C.SENS_FIELDS) & set(C.RICH_FIELDS)),
      "overlap: {}".format(sorted(set(C.SENS_FIELDS) & set(C.RICH_FIELDS))))
check("the prompt does not ask the model for `sensitivity` either",
      '"sensitivity"' not in C.SENS_PROMPT)

print()
print("2. every field it writes is one the prompt actually asks for")
for f in C.SENS_FIELDS:
    check("prompt asks for {!r}".format(f), '"{}"'.format(f) in C.SENS_PROMPT)
check("the prompt asks for `confidence`, which the store records",
      '"confidence"' in C.SENS_PROMPT)

print()
print("3. its opinion is stored apart from the other passes'")
src = C.SOURCE + "-sensitivity"
check("source id differs from the main pass", src != C.SOURCE)
check("source id differs from the rich pass", src != C.SOURCE + "-rich")

print()
print("4. the resume marker is a field that actually gets written")
# main() skips a hash whose `marker` tag already exists for this source. A
# marker that is never written means every re-run re-pays for every file.
check("`nudity` is in the fields, so the marker is recorded",
      "nudity" in C.SENS_FIELDS)

print()
print("5. booleans are asked for as strings")
# store.tag writes str(value), and main() writes any value that is not "".
# A JSON `false` would therefore be stored as the string "False", which no
# consumer looks for, while reading as truthy in most languages.
check("`sexual` is specified as \"yes\"/\"no\", not a JSON boolean",
      '"sexual":"no"' in C.SENS_PROMPT.replace(" ", ""),
      "a bare boolean would be stored as the string 'False'")
check("the prompt says exactly \"yes\" or \"no\"",
      "exactly \"yes\" or \"no\"" in C.SENS_PROMPT)

print()
print("6. the innocent cases are named, because a broad question over-reports")
# The first description sweep produced 33 hits and every one was a false
# positive - bar maps, a "naked cake", Sistine Chapel frescoes. A prompt that
# does not name swimwear and bathing children will do the same at scale.
for phrase in ("swimwear", "nappy", "toddler in bath", "statue"):
    check("prompt names the innocent case {!r}".format(phrase),
          phrase in C.SENS_PROMPT)
check("a child is defined by an age, not left to the model",
      "under about 13" in C.SENS_PROMPT)
check("adult and child are separable in the answer",
      "subject_age" in C.SENS_FIELDS)

print()
print("7. the two passes cannot be run as one")
# --rich and --sensitivity have different prompts, fields and source ids.
# Silently picking one would store one pass's answers under the other's name,
# which is exactly how the rich pass nearly shipped the five-word prompt.
env = dict(os.environ, GOOGLE_API_KEY="test-key-not-used")
cp = subprocess.run(
    [sys.executable, os.path.join(REPO, "stages", "05_enrich",
                                  "classify_live.py"),
     "--thumbs", os.path.join(HERE, "fixtures"),
     "--store", os.path.join(HERE, "fixtures"),
     "--rich", "--sensitivity", "--dry-run"],
    capture_output=True, text=True, env=env, timeout=120)
out = (cp.stdout or "") + (cp.stderr or "")
check("--rich with --sensitivity refuses to run", cp.returncode != 0,
      "exit {}".format(cp.returncode))
check("and says why", "one at a time" in out, out.strip()[-120:])

print()
print("8. a candidate-level filter is COUNTED, never silently dropped")
# Observed live on 2026-09-18, on the 13 files that survived every run of the
# rich pass: Gemini replied `finishReason: RECITATION`, `content: {}`, with
# promptFeedback EMPTY - "filtered because it may contain material that
# resembles existing copyrighted works".
#
# call() checked only promptFeedback.blockReason, so it saw nothing and returned
# txt="". The worker's `if not txt: continue` then dropped the file without
# incrementing ok, fail OR blocked: 1,899 requested reported 1,883 + 3, and
# nothing said where the other 13 went. Learning 41's shape - a falsy return
# read as success - and the reason this is a test rather than a comment is
# learning 44: nobody would ever see this path fire again until it mattered.
import json as _json                                              # noqa: E402
import urllib.request as _ur                                      # noqa: E402


class _FakeResp:
    """Just enough of the urlopen contract: a context manager with read()."""

    def __init__(self, payload):
        self._b = _json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _with_response(payload, **kw):
    """Run call() against a canned response. Returns (result, error string)."""
    real = _ur.urlopen
    try:
        _ur.urlopen = lambda *a, **k: _FakeResp(payload)
        try:
            return C.call([], "key-is-never-used", prompt="x", **kw), ""
        except RuntimeError as e:
            return None, str(e)
    finally:
        _ur.urlopen = real


RECITATION = {
    "candidates": [{"content": {}, "finishReason": "RECITATION", "index": 0}],
    "usageMetadata": {"promptTokenCount": 1515, "totalTokenCount": 1515},
    "modelVersion": "gemini-3.1-flash-lite",
}
_, err = _with_response(RECITATION)
check("a RECITATION finish raises instead of returning empty text",
      bool(err), err or "call() returned normally")
check("it is raised as BLOCKED, which the worker already counts",
      err.startswith("BLOCKED"), err)
check("and the message names the finishReason", "RECITATION" in err, err)

_, err = _with_response({"candidates": [], "usageMetadata": {}})
check("a reply with NO candidates also raises", bool(err), err)
check("and says so rather than naming a reason it does not have",
      "no candidates" in err, err)

# The other half of the guard: a good reply must still pass straight through,
# or this fix would turn 80,884 working files into 80,884 exceptions.
GOOD = {
    "candidates": [{"content": {"parts": [{"text": '{"description":"a dog"}'}]},
                    "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 7},
}
got, err = _with_response(GOOD)
check("a normal reply still returns its text and token counts",
      got == ('{"description":"a dog"}', 5, 7), "{!r} err={!r}".format(got, err))

# A blocked PROMPT still reports the way it always did.
_, err = _with_response({"promptFeedback": {"blockReason": "SAFETY"}})
check("a blocked prompt still raises BLOCKED: SAFETY",
      err == "BLOCKED: SAFETY", err)

print()
if FAILURES:
    print("FAILED {} check(s):".format(len(FAILURES)))
    for f in FAILURES:
        print("  - {}".format(f))
    sys.exit(1)
print("all checks passed")
