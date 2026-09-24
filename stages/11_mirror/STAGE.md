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
| `stages/11_mirror/apply_mirror_deletions.py` | make the SOURCE match the MIRROR, for when a human deleted from H: on purpose. This inverts the trust direction the rest of the stage relies on, which is why it is its own tool and carries three guards: a floor, so an unmounted or half-synced mirror cannot authorise a mass deletion; the mirror JOURNAL rather than the diff decides what counts as a deletion, because a file that failed to upload is indistinguishable from one the user removed and deleting it destroys the only copy; and an exclude list for trees that live on D: by design, like `_Catalog` holding the 124,382-row manifest. Hashes and journals every file BEFORE the unlink, because these have no surviving copy and the journal is the only thing that will ever say what was there. Adds nothing to the no-reingest list: removed is not purged-forever |
| `stages/11_mirror/unmirror_deleted.py` | remove from Drive the copies the library no longer holds. The mirror only ever ADDS, so after the 2026-09-20 dedupe D: held 81,449 and Drive still held 82,685. Deliberately does NOT re-hash: every read of a Drive path hydrates the placeholder and downloads it (learning 5), and identity was already proven twice - `dedupe_library.py` re-hashed victim against keeper at the unlink, and `verify_drive_md5.py` matched both against Google's own checksum. Instead it refuses to remove a victim whose KEEPER is absent from Drive, and refuses one whose size no longer matches the mirror journal. Plain paths, never `\\?\`, which is what breaks on the mount (learning 59) |
| `stages/11_mirror/patch_mirror_flatten.py` | repoint the mirror journal after `flatten_months.py` moved 66,047 files on each copy. The inventory records were repointed that day and this journal was not, so `--status` claimed 66,047 files still to send of a library that was already completely mirrored and proven against Google's md5. The uploader would not have re-sent them - it would have found them present and rewritten 66,113 `written` rows, each carrying the blake2b and md5 computed on the bytes as they were written, as `already-present`, which carries no digest at all because it is a SIZE check on a mount. The cost of the staleness was never bandwidth, it was trading the only evidence that crosses the network boundary in the right direction for a size comparison against a local cache. Repoints only when BOTH sides moved together and counts the one-sided rows rather than guessing at them; refuses a flatten journal that parses to zero moves, because an empty map and a library needing no patch look identical |
| `stages/11_mirror/verify_drive_md5.py` | prove the cloud copy by GOOGLE'S server-side `md5Checksum`, the only check that crosses the network boundary in the right direction. Pages the whole Drive once (~83 requests, not 82,104 lookups), caches the listing as JSONL with an fsync per page so a kill costs nothing, reconstructs every path from parent IDs rather than matching filenames, and refreshes the gcloud token on a 401 |
| `stages/11_mirror/verify_drive_by_mount.py` | prove the cloud copy with NO TOKEN, by reading it back through the mount and hashing. Learning 25 says writing into a Drive mount proves nothing because the bytes sit in a local cache - reading is the same coin the other way up, and the direction matters: a file NOT cached is FETCHED FROM GOOGLE to satisfy the read, so its hash compares Google's bytes against the digest computed on the bytes sent. It cannot promise every read crossed the network (a cached file is read locally), so it PRINTS THE THROUGHPUT as the evidence for that claim rather than asserting it: 2,312 KB/s sustained over 1.15 GB is not an NVMe. 444 of 444 matched, 0 mismatched; the 56 'absent' are `_Review` and `Archive` files Krish deleted from BOTH copies on 2026-09-21 and are absent from D: too |

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
| 76 | the cloud copy is proven by READING it back through the mount, and the tool prints the throughput rather than claiming the network | `code:stages/11_mirror/verify_drive_by_mount.py:judge for yourself`, `test:tests/test_mirror_to_h.py:a mount path is returned unchanged` |
| 5 | a cloud mount's placeholders and free space are not what they look like | prose-only HERE; enforced in 02 ingest by `code:stages/02_ingest/ingest_from_h.py:learning 5` |
| 17 | capacity comes from the account, not the mount | prose-only |
| 25 | receipt is proven by the Drive client's operations queue | `code:stages/11_mirror/move_audio_to_h.py:operations` |
| 59 | the long-path prefix stops at the mount, whose drive letter comes from `--dest` | `code:stages/11_mirror/mirror_to_h.py:MOUNT_DRIVE`, `test:tests/test_mirror_to_h.py:a mount path is returned unchanged` |
| 62 | the floor and the largest permitted file must fit in the volume together, or the throttle can never open | `code:stages/11_mirror/mirror_to_h.py:CACHE_FLOOR_GB + MAX_FILE_GB`, `test:tests/test_mirror_to_h.py:the floor plus the largest permitted file fit in the measured headroom` |
| 66 | a mirror that only adds diverges silently, so removal is explicit machinery rather than absent code | `code:stages/11_mirror/unmirror_deleted.py:the KEEPER still exists on Drive` |
