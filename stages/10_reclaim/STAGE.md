# 10 reclaim

Free space by removing bytes that provably exist elsewhere - and nothing else.
The only stage that destroys data, so the most guarded.

## Inputs
- the library, sources outside it, hash and inode evidence

## Outputs
- deletions, each journalled with its evidence before the unlink

## Invariants
- deletion goes through the allowlist guard; camera originals are protected
- a duplicate needs identical content AND a distinct inode
- the journal row is fsynced before the file is removed
- the survivor is re-hashed at the moment of deletion

## Code
| file | role |
|---|---|
| `contentarchives/safety.py` | the deletion allowlist, the reusable core |
| `scripts/guarded_delete.py` | the only sanctioned delete |
| `scripts/reclaim_duplicates.py` | remove duplicates, keeping the settled copy |
| `scripts/reclaim_d_originals.py` | redundant, hardlinked, or ONLY - by inode |
| `scripts/purge_redundant.py` | delete byte-identical copies, re-verified |
| `scripts/purge_downgrades.py` | delete re-encodes worse than what is held |
| `scripts/free_wins.py` | the reclaim that needs no judgement |
| `scripts/audit_deletions.py` | every journalled deletion carries its evidence |
| `scripts/full_deletion_audit.py` | the exhaustive audit across every journal |
| `scripts/check_scratch_safe.py` | prove scratch holds nothing unique |
| `scripts/clear_scratch.py` | empty scratch only after that proof |
| `scripts/space_audit.py` | where the bytes are, counted by inode |
| `scripts/space_tiers.py` | freeable bytes by how much judgement each needs |
| `scripts/already_in_library.py` | files whose content is already safely held |

## Tests
- `tests/test_safety_and_dedupe.py`

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 1 | a path is never grounds to delete | `guard:contentarchives/safety.py:class Guard`, `test:tests/test_safety_and_dedupe.py:def test_guard_refuses_the_file_that_was_actually_lost` |
| 18 | the journal is written and fsynced before the delete | `code:scripts/guarded_delete.py:fsync` |
| 22 | equal size is not equal content | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
| 28 | two names for one inode are not two copies | `code:scripts/reclaim_d_originals.py:st_ino` |
| 32 | a deletion plan has three outcomes: redundant, hardlink, only copy | `code:scripts/reclaim_d_originals.py:st_ino` |
| 36 | name plus size never declares a duplicate | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
