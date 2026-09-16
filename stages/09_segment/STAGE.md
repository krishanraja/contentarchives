# 09 segment

Decide what the chronology may contain: Personal or Communal by origin folder,
and non-memories moved to `_Review` - moved, never deleted.

## Inputs
- the library, the origin map, the classifier's kind and keep fields

## Outputs
- files moved between `Pending-Segmentation`, `Personal`, `Communal`, `_Review`,
  `Archive`, `ContentProduction`, each move journalled and reversible

## Invariants
- a split is decided per origin folder, reviewed, then applied
- `_Review` is emptied by Krish, never by a rule
- a file's own name outranks a pattern recognised in it

## Code
| file | role |
|---|---|
| `scripts/propose_split.py` | propose Personal/Communal by origin folder, for review |
| `scripts/apply_split.py` | apply an approved split, journalled |
| `scripts/classify_screenshots.py` | separate screenshots from photographs, deleting neither |
| `scripts/move_to_review.py` | move a named set into _Review |
| `scripts/restore_from_review.py` | put back what a rule should never have evicted |
| `scripts/review_patterns.py` | characterise what _Review holds before acting |
| `scripts/to_content_production.py` | move produced content out of the chronology |
| `scripts/triage_downgrades.py` | move re-encoded copies out, keep the originals |
| `scripts/migrate_layout.py` | restructure the library and rewrite every record in step |
| `tools/audit_split.py` | stress-test a split at the level it was decided |

## Tests
- none yet: the split is audited at run time by `audit_split.py` (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 2 | folder names are a hint for review, never a decision | `code:tools/audit_split.py:Stress-test` |
| 20 | filename term boundaries are "not a letter", not \b | `code:guards/profile.py:def is_personal`, `test:tests/test_profile.py:a term inside an underscored filename matches` |
| 21 | a resolution is evidence only by aspect ratio | `code:scripts/classify_screenshots.py:aspect` |
| 29 | a self-declaring filename outranks a recognised pattern | prose-only |
| 30 | \b treats underscore as a letter in filename patterns | `code:guards/profile.py:def is_personal`, `test:tests/test_profile.py:a term inside an underscored filename matches` |
| 54 | a term is dropped for being too broad only after counting what it matches | `test:tests/test_profile.py:def test_no_term_is_too_broad` |
