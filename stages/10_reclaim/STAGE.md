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
| `stages/10_reclaim/guarded_delete.py` | the only sanctioned delete |
| `stages/10_reclaim/reclaim_duplicates.py` | remove duplicates, keeping the settled copy |
| `stages/10_reclaim/reclaim_d_originals.py` | redundant, hardlinked, or ONLY - by inode |
| `stages/10_reclaim/purge_redundant.py` | delete byte-identical copies, re-verified |
| `stages/10_reclaim/build_purge_list.py` | name every file a purge may destroy, individually, and refuse a count that has drifted |
| `stages/10_reclaim/purge_content.py` | destroy chosen content and its traces - the one deletion with NO surviving copy, so it cannot use `guarded_delete` and must not weaken it |
| `stages/10_reclaim/purge_downgrades.py` | delete re-encodes worse than what is held |
| `stages/10_reclaim/free_wins.py` | the reclaim that needs no judgement |
| `stages/10_reclaim/audit_deletions.py` | every journalled deletion carries its evidence |
| `stages/10_reclaim/full_deletion_audit.py` | the exhaustive audit across every journal |
| `stages/10_reclaim/check_scratch_safe.py` | prove scratch holds nothing unique |
| `stages/10_reclaim/clear_scratch.py` | empty scratch only after that proof |
| `stages/10_reclaim/space_audit.py` | where the bytes are, counted by inode |
| `stages/10_reclaim/space_tiers.py` | freeable bytes by how much judgement each needs |
| `stages/10_reclaim/already_in_library.py` | files whose content is already safely held |

## Tests
- `tests/test_safety_and_dedupe.py`
- `tests/test_purge_content.py` - the one tool here that destroys unique content
  on purpose, so the one that must never be trusted untested: a stale list stops
  the WHOLE run and not just the bad row, `--also` refuses by hash a path that is
  not a target, a purged face row keeps its position and its frozen cluster id
  while its embedding is zeroed, and the zero vector still decodes to 512
  float16s because an empty field would drop the row out of
  `cluster_faces.load()`'s filter and shift every position after it

## Edge cases

One-off investigations, kept as playbooks rather than machinery (Krish,
2026-09-16). Each is the recorded answer to a question about freeing space, and
every one of them exists because an obvious-looking reclaim was wrong.

| script | the question it answered | what it found |
|---|---|---|
| `stages/10_reclaim/free_wins.py` | what can be reclaimed with no judgement at all? | 8.99 GB: a commercial film, and one half of a re-muxed pair proven identical by duration and creation time. Everything else needed a human. |
| `stages/10_reclaim/space_audit.py` | where are this volume's bytes actually going? | count by inode, never by name: 879.5 GB of real data read as 1,202.0 GB counted by path, a phantom 322.5 GB (learning 28). |
| `stages/10_reclaim/space_tiers.py` | how much judgement does each freeable tier need? | sort by judgement required, then start at the tier that needs none. |
| `stages/10_reclaim/already_in_library.py` | which freeable files are already safely held? | content-hash proof, not path similarity - the question that precedes any deletion plan. |
| `stages/10_reclaim/audit_deletions.py` | does every journalled deletion carry its evidence? | run after any purge; 46,430 deletions, 0 without evidence at the last run. |
| `stages/10_reclaim/full_deletion_audit.py` | the same question across every journal at once | the exhaustive version, for when a category rather than a file is in doubt. |
| `stages/10_reclaim/check_scratch_safe.py` | does this scratch tree hold anything unique? | must pass before `clear_scratch.py` runs. A scratch directory is only scratch if it is provably a copy. |

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 1 | a path is never grounds to delete | `guard:contentarchives/safety.py:class Guard`, `test:tests/test_safety_and_dedupe.py:def test_guard_refuses_the_file_that_was_actually_lost` |
| 18 | the journal is written and fsynced before the delete | `code:stages/10_reclaim/guarded_delete.py:fsync` |
| 22 | equal size is not equal content | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
| 28 | two names for one inode are not two copies | `code:stages/10_reclaim/reclaim_d_originals.py:st_ino` |
| 32 | a deletion plan has three outcomes: redundant, hardlink, only copy | `code:stages/10_reclaim/reclaim_d_originals.py:st_ino` |
| 36 | name plus size never declares a duplicate | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
| 57 | a purge is keyed on CONTENT, so every derived copy of a blocked hash goes with it - not only the copies it can unlink | `code:stages/10_reclaim/purge_content.py:def sweep_set`, `test:tests/test_purge_content.py:the sweep covers blocked hashes, not just deletable ones` |
