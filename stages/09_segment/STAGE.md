# 09 segment

Decide what the chronology may contain: Personal or Communal by origin folder,
and non-memories moved to `_Review` - moved, never deleted.

## Inputs
- the library, the origin map, the classifier's kind and keep fields

## Outputs
- files moved between `Pending-Segmentation`, `Personal`, `Communal`, `_Review`,
  `Archive`, `ContentProduction`, each move journalled and reversible

## Invariants
- a split is decided per origin folder, reviewed, then applied - **except for
  material that has no origin folder, where Krish decided a PATH rule on
  2026-09-18**: `bharti`, `bhasker` or `Users\Raja` anywhere in the path means
  Communal, everything else Personal. 12,901 of the 21,821 unsided files carry
  no origin folder at all, spanning 1995-2026, so the folder handle that makes
  this stage tractable simply does not exist for them. This is a deliberate
  departure from learning 2 ("folder names are a hint for review, never a
  decision"), taken knowingly and on his instruction, and it applies ONLY to the
  `Media\Pending-Segmentation` and `Media\NoDate` queues
- **a file already sitting in a Communal folder is never demoted to Personal.**
  Somebody put it there; the rule is for material nobody has judged yet
- `Archive`, `_Review` and `ContentProduction` keep their own trees. Krish,
  2026-09-18: those 1,606 files stay where they are and stay out of both naming
  games - `ContentProduction` is produced work, not memories
- `_Review` is emptied by Krish, never by a rule
- a file's own name outranks a pattern recognised in it
- **"for Bharti" on a cluster means its photographs belong in Communal. A
  photograph that merely CONTAINS Bharti does not.** Krish, 2026-09-17: *"all
  'for Bharti' photos definitely belong in Communal, but all photos of Bharti do
  not necessarily belong in Communal"*. She is his mother and appears in 5,087
  of his own photographs, so `person = Bharti` is not a Communal signal - using
  it as one would move a large slice of the Personal chronology to the wrong
  side. The Communal signal is the ANSWER he gave about a cluster
  (`needs_identifying = Bharti`, recorded from "for Bharti"), not the person
  detected in the frame.

## Code
| file | role |
|---|---|
| `contentarchives/sides.py` | `side_of` and `is_majority_communal` - the ONE definition of whose life a photograph is from, read from the path and never from `files.side` |
| `stages/09_segment/propose_split.py` | **BROKEN, do not run.** Proposes by origin folder, which 12,901 unsided files do not have, and its `COMMUNAL` pattern is still the retired publisher's pseudonyms (`PERSON-A\|PERSON-B\|PERSON-C`), so it matches nothing real and would propose "personal" or "unclear" for everything |
| `stages/09_segment/propose_split_by_path.py` | propose a side per FILE for the `Media\Pending-Segmentation` and `Media\NoDate` queues, by Krish's path rule, for review - writes `SPLIT-BY-PATH.csv` and moves nothing |
| `stages/09_segment/review_split_by_path.py` | the proposal as GROUPS of photographs with thumbnails, not rows of paths - because 18,985 CSV rows is a rubber stamp, not a review ("what am i supposed to do in that sheet?") |
| `stages/09_segment/apply_split.py` | **STALE, do not run.** Applies a split journalled and reversible, but joins `ORIGIN-MAP.csv` to `SPLIT-PROPOSAL.csv` by origin folder and builds destinations from the PRE-MIGRATION layout (`LIBROOT\Library\...`, `LIBROOT\NoDate\...`). `migrate_layout.py` has since restructured the library to `Media\<Side>\...`, so every destination it computes is wrong |
| `stages/09_segment/classify_screenshots.py` | separate screenshots from photographs, deleting neither |
| `stages/09_segment/move_to_review.py` | move a named set into _Review |
| `stages/09_segment/restore_from_review.py` | put back what a rule should never have evicted |
| `stages/09_segment/review_patterns.py` | characterise what _Review holds before acting |
| `stages/09_segment/to_content_production.py` | move produced content out of the chronology |
| `stages/09_segment/triage_downgrades.py` | move re-encoded copies out, keep the originals |
| `stages/09_segment/migrate_layout.py` | restructure the library and rewrite every record in step |
| `tools/audit_split.py` | stress-test a split at the level it was decided - stays in `tools/`, which is where every stage's operator-facing utility lives (04 inventory keeps four there, 12 canon three) |

## Tests
- none yet: the split is audited at run time by `audit_split.py` (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 2 | folder names are a hint for review, never a decision | `code:tools/audit_split.py:Stress-test` |
| 20 | filename term boundaries are "not a letter", not \b | `code:guards/profile.py:def is_personal`, `test:tests/test_profile.py:a term inside an underscored filename matches` |
| 21 | a resolution is evidence only by aspect ratio | `code:stages/09_segment/classify_screenshots.py:aspect` |
| 29 | a self-declaring filename outranks a recognised pattern | prose-only |
| 30 | \b treats underscore as a letter in filename patterns | `code:guards/profile.py:def is_personal`, `test:tests/test_profile.py:a term inside an underscored filename matches` |
| 54 | a term is dropped for being too broad only after counting what it matches | `test:tests/test_profile.py:def test_no_term_is_too_broad` |
| 54 | every person named in the journal is protected, asserted through is_personal | `test:tests/test_profile.py:def test_every_named_person_is_protected` |
