# 04 inventory

Describe what is on disk now and where every file came from, counted from the
disk and reconciled against the records.

## Inputs
- the library on disk, the ingest manifest, the hash index

## Outputs
- `INVENTORY.csv` (one row per file, with technical metadata)
- the origin map, and `state/` counts via 12 canon

## Invariants
- the disk is the truth; records are claims about it
- a missing tool is loud, never an empty field
- a count of exactly zero is investigated before it is believed

## Code
| file | role |
|---|---|
| `stages/04_inventory/build_inventory.py` | one row per library file, with every signal about it |
| `stages/04_inventory/patch_inventory_moves.py` | rewrite moved paths from a mover's journal instead of rewalking the library - seconds at constant memory, and it keeps the EXIF and duration a fresh walk would recompute or discard. Writes a temp file and promotes only after checking every destination against the FILESYSTEM |
| `stages/04_inventory/reconcile_disk.py` | find what the records missed |
| `stages/04_inventory/enrich_origin_status.py` | whether an origin still exists, and what deleting it frees |
| `stages/04_inventory/big_files.py` | the largest files, surfaced for review |
| `tools/check_manifest.py` | every manifest row still points at a file, or is explained |
| `tools/origin_map.py` | where every library file came from |
| `tools/track.py` | derive project state from artefacts on disk |
| `tools/verify_inventory.py` | re-probe videos and check the inventory recorded the truth |

## Tests
- none yet: covered only by `verify_inventory.py` at run time (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 4 | an extension is sanity-checked against size | `code:stages/04_inventory/build_inventory.py:learning 4` |
| 8 | compression settings are per source and measured (compression is abandoned) | prose-only |
| 16 | the manifest is reconciled against the disk, absences explained | `code:tools/check_manifest.py:accepted-absences` |
