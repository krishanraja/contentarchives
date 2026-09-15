# 02 ingest

Put a source's files into the library once: content-deduplicated, hardlinked
where the volume allows, resumable across kills.

## Inputs
- a source chosen by 01 sources
- the library, and its size and hash indexes

## Outputs
- files placed under `Media\` (dated by 03, sided later by 09)
- journals of what was added and what was rejected as a duplicate

## Invariants
- a duplicate is only ever declared on a whole-file hash
- the dedup index covers the whole library and says what it covers
- a batch that stages data cleans up loudly, or halts

## Code
| file | role |
|---|---|
| `contentarchives/dedupe.py` | three-tier duplicate detection, the reusable core |
| `scripts/autopilot.py` | the ingest engine: streaming archives, dedupe, dating, placement |
| `scripts/driver.py` | loop autopilot passes and survive the memory watchdog |
| `scripts/runner.py` | run ingest stages sequentially with measured ETAs |
| `scripts/ingest_tree.py` | ingest any folder tree, deduped and dated |
| `scripts/ingest_from_h.py` | stream a cloud mount in batches, routed and resumable |
| `scripts/extract_zip_media.py` | stream out only archive members not already held |
| `scripts/ingest_eta.py` | projected finish time, weighted by bytes |
| `scripts/diagnose_new.py` | ask why an ingest calls everything new |
| `scripts/lib_size_index.py` | size index of the whole library, from disk every time |
| `scripts/check_tiny.py` | what a size threshold would have discarded |
| `scripts/validate_router.py` | test routing rules against known folders |
| `scripts/verify_h_batch.py` | prove a pulled batch landed, by count and hash |
| `scripts/verify_dupes.py` | re-verify a duplicate claim by whole-file hash |
| `scripts/test_dedup.py` | the archive dedup path is content-proven |

## Tests
- `tests/test_safety_and_dedupe.py`

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 5 | cloud placeholders are detected, not skipped | `code:scripts/ingest_from_h.py:learning 5` |
| 7 | size rules out, only a hash rules in | `guard:contentarchives/dedupe.py:class Index`, `test:tests/test_safety_and_dedupe.py:def test_novel_size_short_circuits_without_io`, `test:tests/test_safety_and_dedupe.py:def test_signature_is_not_trusted_alone` |
| 11 | same-volume files enter as hardlinks | `code:scripts/autopilot.py:hardlink` |
| 22 | equal size is not equal content | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
| 23 | a destination map is proven injective before writing | prose-only |
| 27 | the index is rebuilt from the whole library, not replayed | `code:scripts/lib_size_index.py:os.walk` |
| 31 | a cleanup that reclaims space must not suppress its errors | `code:scripts/ingest_from_h.py:rmtree with ignore_errors=True hides its` |
| 36 | name plus size is never a duplicate verdict | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
