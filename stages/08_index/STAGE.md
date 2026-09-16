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

## Code
| file | role |
|---|---|
| `stages/08_index/build_db.py` | build library.db from every source of truth |
| `stages/08_index/master_sheet.py` | one row per file, everything known about it |

## Tests
- `tests/test_build_db.py`

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 42 | the database is replaced atomically | `code:stages/08_index/build_db.py:os.replace` |
| 49 | a group photograph keeps every person in it | `test:tests/test_build_db.py:a group photograph keeps everybody in it` |
