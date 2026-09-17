# 11 mirror

Put the library in a second and third place, and prove it arrived - through the
destination's own evidence, never by reading back what was just written.

## Inputs
- the segmented, reclaimed library

## Outputs
- the library on another drive, and on H: in the cloud, with checksums recorded

## Invariants
- a cloud copy is verified by the cloud's checksum or the client's upload queue
- a mount's free space and contents are the local cache's, not the account's
- nothing leaves Elements until two verified copies exist elsewhere

## Code
| file | role |
|---|---|
| `stages/11_mirror/migrate_library.py` | move the library to a bigger drive, verified |
| `stages/11_mirror/postswap_check.py` | after a drive-letter swap, prove the new disk is the library |
| `stages/11_mirror/move_audio_to_h.py` | move to a cloud mount, deleting only once the queue proves receipt |
| `stages/11_mirror/mirror_to_h.py` | mirror the whole library to H: - driven from the index, append-only journal so a kill costs minutes, blake2b AND md5 computed on the bytes written (never read back through the mount), throttled on the DriveFS queue and the cache floor |
| `stages/11_mirror/chain_mirror_h.ps1` | run the mirror supervised, and resume after the kills this machine hands out - its Postcondition FAILS while files remain, which is what makes the task restart |

## Tests
- none yet for the upload itself: `mirror_to_h.py` is new (2026-09-18) and its
  guards are watched at run time by `chain_mirror_h.ps1` - a one-file probe
  before committing to 925 GB, a `-Verify` that re-derives sampled hashes from
  the SOURCE rather than reading the mount, and a Postcondition that refuses to
  call a partial upload finished. **Still debt:** nothing yet compares the
  server-side `md5Checksum`, so the mirror is uploaded and not verified until
  a Drive-scoped credential exists

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 5 | a cloud mount's placeholders and free space are not what they look like | prose-only HERE; enforced in 02 ingest by `code:stages/02_ingest/ingest_from_h.py:learning 5` |
| 17 | capacity comes from the account, not the mount | prose-only |
| 25 | receipt is proven by the Drive client's operations queue | `code:stages/11_mirror/move_audio_to_h.py:operations` |
