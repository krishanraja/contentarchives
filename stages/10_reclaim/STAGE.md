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
| `stages/10_reclaim/purge_content.py` | destroy chosen content and its traces - the one deletion with NO surviving copy, so it cannot use `guarded_delete` and must not weaken it. `--traces-only --blocklist-also <csv>` sweeps the derived copies of hashes whose files are ALREADY GONE and deletes nothing: `verify()` re-hashes every target at the instant of deletion, so a vanished file fails as "already gone" and can never be a target, which is how 7 thumbnails, 5 face vectors, 5 bounding boxes and 117 tag rows outlived the content they described |
| `stages/10_reclaim/clear_h_sources.py` | delete the consumed H: sources, protecting every file not traced into the library by `ORIGIN-MAP.csv`. Hashing a Drive placeholder downloads it, so `guarded_delete`'s re-hash is unaffordable here (495 GB through a 131 GB cache); the weaker evidence standard is recorded in the journal rather than hidden, and Drive's 30-day trash is the undo |
| `stages/10_reclaim/verify_h_source_held.py` | which H: source files the library can prove it holds, by provenance from `ORIGIN-MAP.csv` first and name+size second - the input `clear_h_sources.py` refuses to run without |
| `stages/10_reclaim/check_h_video_copies.py` | size and name evidence for the videos the clear protected, keeping `__vN` variants and GoPro chapters apart from true duplicates |
| `stages/10_reclaim/verify_h_video_copies.py` | prove those videos byte-identical before anything is deleted - equal size is not equal content. Appends and fsyncs per file and resumes, because the first version held every verdict in memory, was killed for low memory after downloading several GB, and lost the whole run |
| `stages/10_reclaim/purge_downgrades.py` | delete re-encodes worse than what is held |
| `stages/10_reclaim/free_wins.py` | the reclaim that needs no judgement |
| `stages/10_reclaim/audit_deletions.py` | every journalled deletion carries its evidence |
| `stages/10_reclaim/full_deletion_audit.py` | the exhaustive audit across every journal |
| `stages/10_reclaim/check_scratch_safe.py` | prove scratch holds nothing unique |
| `stages/10_reclaim/clear_scratch.py` | empty scratch only after that proof |
| `stages/10_reclaim/space_audit.py` | where the bytes are, counted by inode |
| `stages/10_reclaim/space_tiers.py` | freeable bytes by how much judgement each needs |
| `stages/10_reclaim/already_in_library.py` | files whose content is already safely held |
| `stages/10_reclaim/purge_audited_sources.py` | delete the source copies the library provably holds, driving `guarded_delete` so both files are re-hashed at the instant of the unlink. Adds the proof the guard cannot know about on its own: deleting E: leaves D: as the ONLY local copy, so "the library holds it" is not enough - a survivor's md5 from `h-mirror.csv` must appear in `drive-listing.jsonl`, Google's own record of what it received. Anything ingested since the last mirror is simply not in the journal yet, so its sources are KEPT until the mirror catches up, which is the correct answer rather than an error |
| `stages/10_reclaim/stage_missing_personal.py` | gather the irreplaceable camera originals into one tree so `ingest_tree.py` (which takes a ROOT) can take them. COPIES, never moves - the originals stay put until the ingest is verified, because the sources are about to be purged on the strength of it. Preserves relative structure, since dating falls back to the FOLDER when EXIF and filename give nothing. Excludes what Krish ruled should be deleted rather than ingested, and names it in the output instead of dropping it silently |
| `stages/10_reclaim/missing_personal_set.py` | how many DISTINCT personal files would be lost, and where each survives. The candidate COUNT overstates it twice over: one photograph in three places is one photograph, and a 1.83 GB downloaded film is not a memory. Groups by CONTENT, hashing the candidates itself - a UNIQUE verdict reached by the size gate never hashed the file, so most rows carry no hash, and grouping on name-plus-size has never been allowed to declare identity here (learnings 22, 36). Produces the list to INGEST before any source is purged |
| `stages/10_reclaim/unique_personal_media.py` | of everything found ONLY outside the library, what is genuinely personal? A UNIQUE verdict means the library lacks those bytes, not that anyone wants them - most are a work laptop's screenshots, a `node_modules` staging folder or a phone's thumbnail cache, and reporting those beside a missing photograph buries the one thing that matters. Splits UNIQUE rows into KEEP-CANDIDATE and NOISE, and is deliberately BIASED TOWARDS KEEPING: anything not positively recognised as noise stays a candidate, because a false keep costs thirty seconds of review and a false ignore destroys the only copy of a photograph. Also why an extension list can never classify: `.mts` is AVCHD video AND the TypeScript module extension, and OneDrive's audit counted 654 "videos" that were source files |
| `stages/10_reclaim/audit_source_tree.py` | does the library already hold these exact bytes? Answers it per file for ANY tree (E:, OneDrive, G:), read-only, deleting and proposing nothing. The reference set is `library.db`, and `content_hash` is IMPORTED rather than reimplemented - `already_in_library.py` computes its own 16-byte digest, which cannot be compared against the index at all. The size gate does the real work: 77,882 distinct library sizes mean a file whose size matches nothing is settled UNIQUE without being read. A file that will not hash is recorded UNREADABLE, never as a non-match - treating a failed hash as "no match" is how 222 GB of byte-identical duplicates were once admitted. Runs in bounded resumable slices because this machine kills long jobs |

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
| 61 | the summary a person approves is computed over the same set the action uses | `code:stages/10_reclaim/purge_content.py:in sweep else r`, `test:tests/test_purge_content.py:the trace sweep ACTS on the same set it COUNTS` |
