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
- a purged hash is refused at ingest, by CONTENT, and the refusal is journalled -
  "forever" is a property of the ingest, not of the delete

## Code
| file | role |
|---|---|
| `contentarchives/dedupe.py` | three-tier duplicate detection, the reusable core |
| `stages/02_ingest/autopilot.py` | the ingest engine: streaming archives, dedupe, dating, placement |
| `stages/02_ingest/driver.py` | loop autopilot passes and survive the memory watchdog |
| `stages/02_ingest/runner.py` | run ingest stages sequentially with measured ETAs |
| `stages/02_ingest/ingest_tree.py` | ingest any folder tree, deduped and dated |
| `stages/02_ingest/ingest_from_h.py` | stream a cloud mount in batches, routed and resumable |
| `stages/02_ingest/extract_zip_media.py` | stream out only archive members not already held |
| `stages/02_ingest/ingest_eta.py` | projected finish time, weighted by bytes |
| `stages/02_ingest/diagnose_new.py` | ask why an ingest calls everything new |
| `stages/02_ingest/lib_size_index.py` | size index of the whole library, from disk every time |
| `stages/02_ingest/check_tiny.py` | what a size threshold would have discarded |
| `stages/02_ingest/route_h.py` | decide chronology / production / archive for a source file; identifying vocabulary comes from the profile |
| `stages/02_ingest/validate_router.py` | test routing rules against known folders |
| `stages/02_ingest/verify_h_batch.py` | prove a pulled batch landed, by count and hash |
| `stages/02_ingest/verify_dupes.py` | re-verify a duplicate claim by whole-file hash |

## Tests
- `tests/test_safety_and_dedupe.py`
- `tests/test_dedup.py`
- `tests/test_route_h.py`
- `tests/test_blocklist_hook.py` - the no-reingest list existed for a day with
  nothing reading it. Pins that a purged hash is refused by content under any
  name, that a file whose SIZE is not blocked is never hashed (proved by making
  `full_hash` raise), that same-size-different-content is still admitted, that
  every refusal is journalled, and that an absent list blocks nothing and says so
- `tests/test_flat_chronology.py` - the chronology was flattened to `YYYY\` on
  2026-09-21 but the WRITERS were not: `place`, the tree walk and
  `ingest_tree.py` all still joined `f"{y}-{m}"`, so the next ingest would have
  rebuilt the month level one file at a time into folders no index, mirror arm
  or reader looks in. Nothing would have failed, which is why it needs a test.
  Pins the flat destination, the month-prefix collision convention taken from
  `flatten_months.py`, and - reading the source, because the bug was four
  copies of one join - that no writer joins a `YYYY-MM` folder again

## Edge cases

One-off investigations, kept as playbooks rather than machinery (Krish,
2026-09-16: "one off investigations need to be stored not as part of core
machinery but how to deal with common edge cases"). Each answered a question
once; the answer is here, the script is there for when the same edge case
recurs, and nobody maintains it as part of the belt.

| script | the question it answered | what it found |
|---|---|---|
| `stages/02_ingest/diagnose_new.py` | why is an ingest calling almost everything new? | the dedup index covered 12% of the library, so nothing matched. Run it against a baseline that excludes the ingest itself, or the answer is circular. |
| `stages/02_ingest/check_tiny.py` | were any files skipped as "too small" actually photographs? | check before a size threshold is trusted, not after: a 1.5 KB `.mts` is app junk, but small `.jpg` files were real. |
| `stages/02_ingest/ingest_eta.py` | when will this ingest finish? | weight by bytes, never by member count - a 40 GB archive of videos and one of screenshots share a file count and nothing else. |
| `stages/02_ingest/verify_dupes.py` | is a head+tail duplicate signature trustworthy? | re-verify by whole-file hash before anything acts on it; the signature rules out, never in. |
| `stages/02_ingest/validate_router.py` | do the routing rules agree with folders whose character is already known? | run it after any change to `route_h.py`, on folders you can judge by eye. |

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 5 | cloud placeholders are detected, not skipped | `code:stages/02_ingest/ingest_from_h.py:learning 5` |
| 7 | size rules out, only a hash rules in | `guard:contentarchives/dedupe.py:class Index`, `test:tests/test_safety_and_dedupe.py:def test_novel_size_short_circuits_without_io`, `test:tests/test_safety_and_dedupe.py:def test_signature_is_not_trusted_alone` |
| 11 | same-volume files enter as hardlinks | `code:stages/02_ingest/autopilot.py:hardlink` |
| 22 | equal size is not equal content | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
| 23 | a destination map is proven injective before writing | prose-only |
| 27 | the index is rebuilt from the whole library, not replayed | `code:stages/02_ingest/lib_size_index.py:os.walk` |
| 31 | a cleanup that reclaims space must not suppress its errors | `code:stages/02_ingest/ingest_from_h.py:rmtree with ignore_errors=True hides its` |
| 36 | name plus size is never a duplicate verdict | `test:tests/test_safety_and_dedupe.py:def test_same_name_same_size_different_content_is_not_a_duplicate` |
| 51 | ingest hashes but never decodes, so 70 undecodable videos entered the library and were found 18 months later by 06 faces - decoding one frame at ingest is not built | prose-only HERE; the census that found them is in 06 faces, `code:stages/06_faces/video_face_frames.py:def marker` |
| 57 | a purged hash is refused at ingest, by content, and the size gates the hash so 88 files cost no throughput | `code:stages/02_ingest/autopilot.py:def is_blocked`, `code:stages/02_ingest/ingest_tree.py:THE NO-REINGEST LIST`, `test:tests/test_blocklist_hook.py:the renamed copy is refused` |
