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
| `stages/05_enrich/store.py` | the enrichment store, keyed by content hash |
| `stages/05_enrich/thumbnail.py` | small thumbnails, because image size is the cost |
| `stages/05_enrich/frames.py` | 2-5 frames per video for the classifier |
| `stages/05_enrich/classify_live.py` | classify with Gemini, live and resumable |
| `stages/05_enrich/batch_classify.py` | classify through a batch API; also lists thumbnail assets |
| `stages/05_enrich/classify.py` | the original single-model classifier |
| `stages/05_enrich/bakeoff.py` | measure which model to use |
| `stages/05_enrich/consensus.py` | score models against a reference they did not write |
| `stages/05_enrich/geocode.py` | coordinates to place names, offline |
| `stages/05_enrich/merge_shards.py` | merge per-worker store shards |
| `stages/05_enrich/geocode_library.py` | give every GPS-tagged file a place name |
| `stages/05_enrich/refix_rotated.py` | regenerate thumbnails built sideways |
| `stages/05_enrich/verify_rotation.py` | check rotated thumbnails are the right way up |
| `stages/05_enrich/verify_rich.py` | check descriptions are descriptions, not labels |
| `stages/05_enrich/audit_sheet.py` | a contact sheet for auditing the classifier by eye |
| `stages/05_enrich/store_summary.py` | what the store holds right now |
| `stages/05_enrich/chain_phase3_resume.ps1` | classification and the photograph face pass, gated |
| `stages/05_enrich/chain_rich.ps1` | the description pass, gated |
| `stages/05_enrich/chain_thumbnails.ps1` | build every missing thumbnail, gated |

## Tests
- none yet: covered at run time by `verify_rich.py` and `verify_rotation.py` (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 35 | a model is chosen on per-item verdicts and a confusion matrix | `code:stages/05_enrich/bakeoff.py:verdict` |
| 37 | model disagreement is recorded, not resolved by another model | `code:stages/08_index/master_sheet.py:KindDisputed` |
| 40 | a spend ceiling survives the restart loop | `code:stages/05_enrich/chain_rich.ps1:CEILING REACHED` |
