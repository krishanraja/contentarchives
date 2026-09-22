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
| `stages/04_inventory/reconcile_disk.py` | find what the records missed - output is always ADDITIVE, never a removal |
| `stages/04_inventory/hash_new_files.py` | hash the library files no hash index has ever seen. The documented chain for new material - `ingest_tree --apply`, `reconcile_disk --write`, `build_db` - computes NO content hash anywhere: ingest_tree hashes only size-collisions, reconcile_disk walks directories, build_db joins `path -> hash` out of CSVs. A row with no hash is not a row with a gap, it is invisible - `backfill_thumbs` drives from the index and reported 116 files to do while 11,707 newly ingested files sat unseen, and with no thumbnail there is no classifier, no face pass and no naming game, so the people in them can never be asked about. The hole opens on EVERY ingest, which is every source still queued in ROADMAP Phase B. Appends only, never overwrites an existing hash (those records cannot be reproduced), and reads both hash files so it does not re-hash 64,683 to learn nothing |
| `stages/04_inventory/drop_removed_rows.py` | drop rows for files a HUMAN deliberately removed, from a NAMED list - absence is a precondition, never the reason. A listed path that still exists stops the whole run. `--block` adds the hash to the no-reingest list, because dropping the row without it means the next phone ingest restores the file |
| `stages/04_inventory/enrich_origin_status.py` | whether an origin still exists, and what deleting it frees |
| `stages/04_inventory/big_files.py` | the largest files, surfaced for review |
| `tools/check_manifest.py` | every manifest row still points at a file, or is explained |
| `tools/origin_map.py` | where every library file came from |
| `tools/track.py` | derive project state from artefacts on disk |
| `tools/verify_inventory.py` | re-probe videos and check the inventory recorded the truth |

## Tests
- `tests/test_drop_removed_rows.py` - the tool that feeds the no-reingest list
  corrupted it on its first use, writing a SIZE into the `Hash` column because
  it read column 1 of headerless `MIGRATION-HASHES.csv` when the layout is
  `path, bytes, hash`. Pins that the hash is found by SHAPE (64 hex) and never by
  position, that the blocklist columns follow their header, that a listed path
  which still exists stops the whole run, and that the original record is kept
  as a `.bak` before any rewrite
- `tests/test_reconcile_rows.py` - `--write` is the documented way new files
  reach the records, and it appended 11,742 rows whose Side was the literal
  string `Media` (a path slice, not `side_of`), whose Year was empty although
  the path names it, and where 4,344 VIDEOS were filed as photographs because
  the `MEDIA` set it tested against holds video extensions too. The append
  succeeded and the counts reconciled; only the meaning was wrong. Pins that
  the side comes from `side_of` and agrees with it, that the year is read from
  the path while a queue gets none invented for it, that a video is never a
  photo, and that `--repair` corrects its own rows while leaving a row written
  by anything else byte for byte
- `build_inventory.py` and the origin map are still covered only by
  `verify_inventory.py` at run time (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 4 | an extension is sanity-checked against size | `code:stages/04_inventory/build_inventory.py:learning 4` |
| 8 | compression settings are per source and measured (compression is abandoned) | prose-only |
| 16 | the manifest is reconciled against the disk, absences explained | `code:tools/check_manifest.py:accepted-absences` |
| 60 | a hash is identified by SHAPE, never by column position | `code:stages/04_inventory/drop_removed_rows.py:def hashlike`, `test:tests/test_drop_removed_rows.py:the hash is the 64-hex value, not the size` |
