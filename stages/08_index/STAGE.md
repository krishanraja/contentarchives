# 08 index

Assemble everything known about every file into one queryable database, with
every opinion kept and human answers always winning.

## Inputs
- `INVENTORY.csv`, the hash index, the store, the answers journal

## Outputs
- `library.db` (files, tags, resolved, photo_people, answers, full-text search)
- `MASTER.csv`

## Invariants
- derived tables are rebuilt every run; the journal is only ever read
- the build writes a temporary database and renames it into place
- a field that can hold several true values (person) holds all of them
- a name a later answer replaced never comes back through the derived tag layer
- **`audience` is DERIVED on every build and never asserted.** `family` when a
  photograph holds someone who also appears in Communal, `private` otherwise,
  and always `private` inside `Media\Personal\Intimate`. Krish, 2026-09-18:
  *"If I classify a personal photo as someone who also belongs in Communal, it
  automatically becomes available by others later down the track"* - so there is
  no default to decide for the 41,124 Personal files with nobody named in them.
  They are not a policy, they are simply not named yet, and naming on a phone
  opens access by itself. **Audience is not side**: stage 09 holds that a
  photograph merely CONTAINING Bharti does not belong in Communal, and audience
  inverts that on purpose - containing her is exactly what she should see

## Code
| file | role |
|---|---|
| `stages/08_index/build_db.py` | build library.db from every source of truth |
| `stages/08_index/embed_descriptions.py` | a vector per description, so the library can be asked in words rather than keywords. `search` is FTS5 and matches SPELLING - it cannot find "we were all squinting into the sun" though a description saying exactly that sits in the row. 85,368 descriptions, gemini-embedding-001 at 768 dims, 24 min, $0.90 measured, 0 failed. The vectors are NOT paired by position with a separate file: each shard is one `.npz` holding its own hashes AND vectors, written once and renamed atomically, because learning 45 is a positional cache that drifted until 11,347 of 11,611 vectors described the wrong photograph. `--ask` prints how much of the library it searched and says plainly that the rest cannot match anything |
| `stages/08_index/build_events.py` | group photographs into EVENTS, because nobody remembers a file. A question answered with twelve frames from the middle of a four-day trip has answered a narrower question than the one asked. An event is a run with no gap longer than 14 hours - TIME is the only signal that separates one wedding from another, and `occasion` cannot: it is a category ("everyday" 28,549, "travel" 23,289) and grouping on it would put every party since 2008 in one bucket. Place, people and occasion then DESCRIBE the event time has already found. 1,388 events over 46,625 photographs; `--ask` searches them and states that 37,296 files have no clock and are in no event |
| `stages/08_index/sample_rebuild.py` | record what the index files do through a rebuild, so a progress signal is chosen from a trace rather than guessed |
| `stages/08_index/master_sheet.py` | one row per file, everything known about it |

## Tests
- `tests/test_build_db.py`

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 77 | the index resolves only hashes the library still holds, so a coverage figure counts the library and not the store | `code:stages/08_index/build_db.py:ONLY FOR FILES THE LIBRARY STILL HOLDS`, `test:tests/test_reconcile_rows.py:a row it did not write is untouched` |
| 42 | the database is replaced atomically | `code:stages/08_index/build_db.py:def promote` |
| 55 | the swap is retried, and a lock is never reported as lost work | `code:stages/08_index/build_db.py:def promote` |
| 49 | a group photograph keeps every person in it | `test:tests/test_build_db.py:a group photograph keeps everybody in it` |
| 54 | a name a later answer replaced never returns through the derived tag layer, and an uncontradicted tag name is never stripped | `code:stages/08_index/build_db.py:superseded`, `test:tests/test_build_db.py:the replaced name is gone from photo_people` |
| 56 | `v_files` is one row per path, so a per-hash question groups instead of joining, and a count above the file count is a fan-out | `code:stages/08_index/build_db.py:GROUP BY f.path`, `test:tests/test_build_db.py:one row per hash, never one row per join` |
| 68 | the index is rebuilt LAST, after the disk and every path record have settled - a rebuild started early captures the old state and looks authoritative | prose-only |
| 69 | a job that recently worked and now dies is measured against the machine before the code is touched | prose-only |
