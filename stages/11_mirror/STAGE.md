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
| `stages/11_mirror/unmirror_deleted.py` | remove from Drive the copies the library no longer holds. The mirror only ever ADDS, so after the 2026-09-20 dedupe D: held 81,449 and Drive still held 82,685. Deliberately does NOT re-hash: every read of a Drive path hydrates the placeholder and downloads it (learning 5), and identity was already proven twice - `dedupe_library.py` re-hashed victim against keeper at the unlink, and `verify_drive_md5.py` matched both against Google's own checksum. Instead it refuses to remove a victim whose KEEPER is absent from Drive, and refuses one whose size no longer matches the mirror journal. Plain paths, never `\\?\`, which is what breaks on the mount (learning 59) |
| `stages/11_mirror/verify_drive_md5.py` | prove the cloud copy by GOOGLE'S server-side `md5Checksum`, the only check that crosses the network boundary in the right direction. Pages the whole Drive once (~83 requests, not 82,104 lookups), caches the listing as JSONL with an fsync per page so a kill costs nothing, reconstructs every path from parent IDs rather than matching filenames, and refreshes the gcloud token on a 401 |

## Tests
- `tests/test_mirror_to_h.py` - the uploader ran 655 GB with no test at all, and
  every bug it had was found by watching it run, which is the most expensive way
  to find any of them. Pins the `\\?\` exemption on the mount (learning 59), that
  `MOUNT_DRIVE` follows `--dest` rather than a hardcoded `H:`, that
  `copy_hashing` reports the bytes it WROTE with both digests, and that the
  journal's column names - which the chain's `-Verify` and `Remaining` parse -
  do not move
- run-time guards in `chain_mirror_h.ps1`: a one-file probe before committing to
  925 GB, a `-Verify` that re-derives sampled hashes from the SOURCE rather than
  reading the mount, and a Postcondition that refuses to call a partial upload
  finished. Those gates were inert until learning 58 was fixed
- **The cloud copy is PROVEN, 2026-09-19:** `verify_drive_md5.py` matched all
  82,100 journalled files against the checksum Google computed on receipt -
  0 missing, 0 mismatched, 0 without a checksum. The debt this section carried
  is paid.
- Two failures worth keeping, because both reported a confident wrong answer:
  the first run said **all 82,100 MISSING**, because Drive's `files.list` never
  returns the account root, so a reconstructed path starts at
  `ContentLibrary/...` while the journal records `H:\My Drive\ContentLibrary\...`
  - a total failure produced entirely by my own key construction, on a mirror
  whose very first probe had already matched an 18.6 GB file byte for byte. And
  the first draft fell back to matching on BASENAME when the prefix was absent,
  which would have confirmed a file sitting in the wrong folder; that fallback
  is now an explicit `UNKEYED` failure, counted in the verdict rather than
  quietly excluded from it

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 5 | a cloud mount's placeholders and free space are not what they look like | prose-only HERE; enforced in 02 ingest by `code:stages/02_ingest/ingest_from_h.py:learning 5` |
| 17 | capacity comes from the account, not the mount | prose-only |
| 25 | receipt is proven by the Drive client's operations queue | `code:stages/11_mirror/move_audio_to_h.py:operations` |
| 59 | the long-path prefix stops at the mount, whose drive letter comes from `--dest` | `code:stages/11_mirror/mirror_to_h.py:MOUNT_DRIVE`, `test:tests/test_mirror_to_h.py:a mount path is returned unchanged` |
