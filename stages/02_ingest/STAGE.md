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
| `stages/02_ingest/route_h.py` | decide chronology / production / archive for a source file; identifying vocabulary comes from the profile |
| `scripts/validate_router.py` | test routing rules against known folders |
| `scripts/verify_h_batch.py` | prove a pulled batch landed, by count and hash |
| `scripts/verify_dupes.py` | re-verify a duplicate claim by whole-file hash |

## Tests
- `tests/test_safety_and_dedupe.py`
- `tests/test_dedup.py`
- `tests/test_route_h.py`

## Edge cases

One-off investigations, kept as playbooks rather than machinery (Krish,
2026-09-16: "one off investigations need to be stored not as part of core
machinery but how to deal with common edge cases"). Each answered a question
once; the answer is here, the script is there for when the same edge case
recurs, and nobody maintains it as part of the belt.

| script | the question it answered | what it found |
|---|---|---|
| `scripts/diagnose_new.py` | why is an ingest calling almost everything new? | the dedup index covered 12% of the library, so nothing matched. Run it against a baseline that excludes the ingest itself, or the answer is circular. |
| `scripts/check_tiny.py` | were any files skipped as "too small" actually photographs? | check before a size threshold is trusted, not after: a 1.5 KB `.mts` is app junk, but small `.jpg` files were real. |
| `scripts/ingest_eta.py` | when will this ingest finish? | weight by bytes, never by member count - a 40 GB archive of videos and one of screenshots share a file count and nothing else. |
| `scripts/verify_dupes.py` | is a head+tail duplicate signature trustworthy? | re-verify by whole-file hash before anything acts on it; the signature rules out, never in. |
| `scripts/validate_router.py` | do the routing rules agree with folders whose character is already known? | run it after any change to `route_h.py`, on folders you can judge by eye. |

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
| 51 | ingest hashes but never decodes, so 70 undecodable videos entered the library and were found 18 months later by 06 faces - decoding one frame at ingest is not built | prose-only HERE; the census that found them is in 06 faces, `code:stages/06_faces/video_face_frames.py:def marker` |
