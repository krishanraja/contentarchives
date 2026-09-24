# 06 faces

Find every face in every photograph and every video frame, group them into
people, and keep the cluster ids Krish's answers point at stable for ever.

## Inputs
- thumbnails and the classifier's people count (photographs)
- every video in `library.db` (video frames, sampled densely)

## Outputs
- `faces.0.csv`, `faces.video.csv`: one row per face, embedding in the row
- `FACE-CLUSTERS.csv`, `FACE-CLUSTERS-VIDEO.csv`: which face is in which cluster
- `CLUSTER-MERGES.csv`: which clusters are one person
- cluster tags in the store

## Invariants
- existing cluster ids are FROZEN: never re-run `cluster_faces.py --apply`; new
  faces join through `assign_video_faces.py`
- an embedding lives in the row that describes it; a positional cache is
  re-derived before use
- a merge that would put two differently-named people together refuses to run
- an unreadable image is recorded as unreadable, never as "no faces"

## Code
| file | role |
|---|---|
| `stages/06_faces/faces_embed.py` | detect and embed faces in thumbnails or video frames |
| `stages/06_faces/video_face_frames.py` | one frame per 30 s from every video, verified from source |
| `stages/06_faces/backfill_cluster_tags.py` | publish a cluster tag for every assigned face, so no sheet can offer a row the store cannot hold |
| `stages/06_faces/cluster_faces.py` | the original clustering; never re-applied |
| `stages/06_faces/merge_clusters.py` | merge clusters that are one person, tested against names |
| `stages/06_faces/assign_video_faces.py` | put video faces into the frozen clusters |
| `stages/06_faces/assign_new_faces.py` | put newly ingested PHOTOGRAPH faces into the frozen clusters. The invariant above had a hole: `assign_video_faces.py` covers faces arriving from video frames, and nothing covered faces arriving from new photographs - which is what every ingest produces - so the only tool that would have taken the 26,646 faces of 2026-09-22 was the one this stage forbids. Same algorithm on the photograph side, and it builds its centroids by JOINING ON (hash, face_index) rather than through `face-emb.npy`: that cache did not exist, and rebuilding a positional artefact to consume it would have rebuilt the hazard learning 45 was paid for. 16,910 of the new faces joined a cluster that already existed and 7,754 inherited a name Krish had already given, naming 4,982 photographs without a question being asked |
| `stages/06_faces/verify_faces.py` | re-derive embeddings from their images |
| `stages/06_faces/sample_missed_faces.py` | how many faces the classifier filter throws away |
| `stages/06_faces/chain_video_faces.ps1` | frames, faces, assign, rebuild, every step gated |

## Tests
- `tests/test_video_faces.py`
- `tests/test_new_face_ids.py` - the frozen-id rule says "never renumber the old
  ids" and says nothing about "never hand out an id somebody else is using",
  which are different rules. `assign_new_faces.py` took its next free id from
  `FACE-CLUSTERS.csv` alone while `assign_video_faces.py` had already allocated
  c44284-c59609 in a SEPARATE file, so 6,970 new photograph clusters landed on
  top of 15,326 video ones and six of them inherited one of Krish's answers -
  one answer, two different people. Pins that the floor is a maximum across
  every allocator, that a lower video maximum cannot drag it down, that a
  missing allocator stops the run rather than being read as zero, and that the
  real library's new ids never reuse a video id

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 71 | a value never means two things: `how` is DERIVED from the id, and centroid space is separate from the new-id base | `code:stages/06_faces/assign_video_faces.py:def how_of`, `test:tests/test_video_faces.py:and how still distinguishes joined from video-only` |
| 72 | a new id clears every file that allocates one, and a missing allocator stops the run | `code:stages/06_faces/assign_new_faces.py:THE NEXT FREE ID MUST CLEAR`, `test:tests/test_new_face_ids.py:the next id clears the VIDEO file too, not just its own` |
| 23 | frame names are unique even for a clip milliseconds long | `code:stages/06_faces/video_face_frames.py:def targets`, `test:tests/test_video_faces.py:distinct paths for a` |
| 33 | every video in the library is in the frame set, missing ones counted | `code:stages/06_faces/video_face_frames.py:missing from disk`, `test:tests/test_video_faces.py:25 of 28 videos missing from disk STOPS the run` |
| 41 | an unreadable frame is recorded as -2, not "no faces" | `code:stages/06_faces/faces_embed.py:face_index -2`, `test:tests/test_video_faces.py:counts 2 to look at, 1 done, 1 unreadable` |
| 45 | the positional cache is GONE from both assigners - they join `faces.0.csv` on (hash, face_index), which is learning 45's own durable fix rather than a guard over the hazard, and a frozen face the photograph file cannot produce REFUSES the run because a centroid built from a partial cluster is a wrong centroid. The guard itself is still live for `merge_clusters.py`, which does still pair by position | `code:stages/06_faces/assign_video_faces.py:partial cluster`, `code:stages/06_faces/assign_new_faces.py:partial cluster`, `test:tests/test_video_faces.py:a frozen face missing from faces.0.csv is refused`, `test:tests/test_guards.py:a drifted cache is caught` |
| 47 | completion is asked of the disk and the store, with --dry-run | `test:tests/test_video_faces.py:--dry-run exits 0 without loading a model`, `code:stages/06_faces/chain_video_faces.ps1:--outstanding` |
| 51 | a frame that will not decode is marked and counted, so the pass doubles as a decode census of every video | `code:stages/06_faces/video_face_frames.py:def marker`, `test:tests/test_video_faces.py:--outstanding counts outstanding/present/failed` |
