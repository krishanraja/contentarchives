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
| `stages/06_faces/cluster_faces.py` | the original clustering; never re-applied |
| `stages/06_faces/merge_clusters.py` | merge clusters that are one person, tested against names |
| `stages/06_faces/assign_video_faces.py` | put video faces into the frozen clusters |
| `stages/06_faces/verify_faces.py` | re-derive embeddings from their images |
| `stages/06_faces/sample_missed_faces.py` | how many faces the classifier filter throws away |
| `stages/06_faces/chain_video_faces.ps1` | frames, faces, assign, rebuild, every step gated |

## Tests
- `tests/test_video_faces.py`

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 23 | frame names are unique even for a clip milliseconds long | `code:stages/06_faces/video_face_frames.py:def targets`, `test:tests/test_video_faces.py:distinct paths for a` |
| 33 | every video in the library is in the frame set, missing ones counted | `code:stages/06_faces/video_face_frames.py:missing from disk`, `test:tests/test_video_faces.py:25 of 28 videos missing from disk STOPS the run` |
| 41 | an unreadable frame is recorded as -2, not "no faces" | `code:stages/06_faces/faces_embed.py:face_index -2`, `test:tests/test_video_faces.py:counts 2 to look at, 1 done, 1 unreadable` |
| 45 | frozen centroids are re-derived before assigning to them | `code:stages/06_faces/assign_video_faces.py:check_alignment`, `test:tests/test_video_faces.py:a cache drifted by one row is refused` |
| 47 | completion is asked of the disk and the store, with --dry-run | `test:tests/test_video_faces.py:--dry-run exits 0 without loading a model`, `code:stages/06_faces/chain_video_faces.ps1:--outstanding` |
| 51 | a frame that will not decode is marked and counted, so the pass doubles as a decode census of every video | `code:stages/06_faces/video_face_frames.py:def marker`, `test:tests/test_video_faces.py:--outstanding counts outstanding/present/failed` |
