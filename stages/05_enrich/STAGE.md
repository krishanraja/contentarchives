# 05 enrich

Say what each file is: thumbnails, sampled frames, a vision model's
classification and description, and place names from GPS.

## Inputs
- the library, `INVENTORY.csv`

## Outputs
- `D:\_thumbs`, the enrichment store `D:\_enrichment\content_tags.csv`

## Invariants
- every opinion is kept with its source; nothing is resolved away in the store
- models are chosen on per-item verdicts, never a scalar
- model agreement is not evidence; disagreement is carried to a human
- spend stops on measured cost, and a restart cannot multiply the budget

## Code
| file | role |
|---|---|
| `engine/store.py` | the enrichment store, keyed by content hash |
| `engine/thumbnail.py` | small thumbnails, because image size is the cost |
| `engine/frames.py` | 2-5 frames per video for the classifier |
| `engine/classify_live.py` | classify with Gemini, live and resumable |
| `engine/batch_classify.py` | classify through a batch API; also lists thumbnail assets |
| `engine/classify.py` | the original single-model classifier |
| `engine/bakeoff.py` | measure which model to use |
| `engine/consensus.py` | score models against a reference they did not write |
| `engine/geocode.py` | coordinates to place names, offline |
| `engine/merge_shards.py` | merge per-worker store shards |
| `tools/geocode_library.py` | give every GPS-tagged file a place name |
| `tools/refix_rotated.py` | regenerate thumbnails built sideways |
| `tools/verify_rotation.py` | check rotated thumbnails are the right way up |
| `tools/verify_rich.py` | check descriptions are descriptions, not labels |
| `tools/audit_sheet.py` | a contact sheet for auditing the classifier by eye |
| `scripts/store_summary.py` | what the store holds right now |
| `scripts/chains/chain_phase3_resume.ps1` | classification and the photograph face pass, gated |
| `scripts/chains/chain_rich.ps1` | the description pass, gated |
| `scripts/chains/chain_thumbnails.ps1` | build every missing thumbnail, gated |

## Tests
- none yet: covered at run time by `verify_rich.py` and `verify_rotation.py` (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 35 | a model is chosen on per-item verdicts and a confusion matrix | `code:engine/bakeoff.py:verdict` |
| 37 | model disagreement is recorded, not resolved by another model | `code:tools/master_sheet.py:KindDisputed` |
| 40 | a spend ceiling survives the restart loop | `code:scripts/chains/chain_rich.ps1:CEILING REACHED` |
