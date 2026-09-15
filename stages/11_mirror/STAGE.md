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
| `scripts/migrate_library.py` | move the library to a bigger drive, verified |
| `scripts/postswap_check.py` | after a drive-letter swap, prove the new disk is the library |
| `scripts/move_audio_to_h.py` | move to a cloud mount, deleting only once the queue proves receipt |

## Tests
- none yet: the H: upload and its verification are not built (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 5 | a cloud mount's placeholders and free space are not what they look like | prose-only |
| 17 | capacity comes from the account, not the mount | prose-only |
| 25 | receipt is proven by the Drive client's operations queue | `code:scripts/move_audio_to_h.py:operations` |
