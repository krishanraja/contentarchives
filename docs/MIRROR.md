# Two copies, proven identical

How `D:` and `H:` end up holding the same library, what order the work happens in,
and where the human gets to look at it before any of it becomes permanent.

There is no second copy of this library today. That is the largest open risk in the
project, on a drive that has already logged controller errors. This document exists so
that fixing it does not become its own accident.

---

## 1. The contradiction, and why it dissolves

Two instructions look incompatible:

- *Everything is going to stay on H. Do not download this stuff to D.*
- *We want two exact copies of the final library on both D and H.*

They only conflict while **the library** and **the material on H** are treated as the
same kind of thing. They are not.

| | What it is | Where it ends up |
|---|---|---|
| **The Library** | `PhotoLibrary\` + `Archive\` + `ContentProduction\` - curated, deduplicated, dated, split | **Identical on D: and H:** |
| **Source material** | `_photo-consolidation\from-boogles`, `from-lorimer`, `from-wd6400`, `in`, `out` | Inputs. Consumed, then retired |

`from-wd6400` is not a copy of the library. It is 140 GB of unprocessed input that has
never been deduplicated against anything. Mirroring it as-is would not produce a second
copy of the library; it would produce a second copy of the mess the library was built
to resolve.

So the answer to *do I have to download what is on H* is: **the bytes must pass through
D:, but they do not stay there unless they belong in the library.**

### Streaming, not downloading

For each source folder on `H:`, in batches:

```
pull batch to D:\_stage  ->  ingest (size prefilter, then whole-file hash)
                         ->  new files enter the library
                         ->  duplicates rejected, staged batch deleted
```

D: permanently gains **only** the files that belong in the library - which it has to
gain anyway, because it is one of the two copies. Everything else is transient. The
staging folder never holds more than one batch, so this costs bandwidth and time, not
disk.

This is not a workaround. It is the only way content-addressed deduplication can work:
**you cannot know whether a file is a duplicate without reading its bytes**, and per
learning 15 those bytes cannot be read off the Drive mount reliably - hashing there
hangs with zero bytes read rather than failing. Copy local first, always.

---

## 2. What has to be true before anything starts

Three gates. Each has been wrong before when assumed.

**Capacity - confirmed, not inferred.** `H:` is a **2 TB** account (confirmed by Krish
2026-09-07). The library is **563 GB today and still growing**, so capacity is not the
constraint and this gate is satisfied.

It is recorded here because the mount actively lies about it: `Get-PSDrive H:` reports
47.3 GB free, which is exactly `C:`'s free space - it is reporting the local cache
volume (learning 17). Any future check must come from the account, never the mount. The
number that still needs a live read before the final mirror is **free** space, not
total: `H:` also carries the OS's working documents and the `_photo-consolidation`
inputs.

**Sync queue empty, before and after.** DriveFS keeps its backlog in
`%LOCALAPPDATA%\Google\DriveFS\<account>\metadata_sqlite_db`, table `operations`. It
currently reads **0**. A copy into the mount lands in the local cache and uploads behind
it; the mount will happily show a file that is not in the cloud (learning 25). The queue
draining to 0 is the only completion signal that means anything.

**`C:` headroom, per batch.** Drive stages every upload through a cache on `C:`. One
563 GB copy fills the system drive and dies partway. Batch it, and check `C:` between
batches.

---

## 3. Order of work, and why this order

```
  1. CONSUME      every source into the library on D:
  2. SEGMENT      split, classify, move documents out
  3. AUDIT        prove the library is what it claims to be
  4. BREAKOUT     the human looks at it   <- changes are still cheap here
  5. MIRROR       D: -> H:
  6. PROVE        both sides identical by content
```

The standing instruction was not to mirror before the audit, and the reason holds:
**mirroring an unaudited library propagates its mistakes**, and doing it before
segmentation means uploading files that are about to move, then uploading them again.

The counter-risk is real too - the library is unbacked *now*, on a drive with a failure
history. These reconcile by treating the two copies as serving different purposes at
different times:

- **A protective copy may be taken at any point** and is not the mirror. It is
  insurance. It is never authoritative and nothing is deleted because of it.
- **The mirror is taken once, after the audit**, and is authoritative.

An incremental mirror converges: bytes uploaded early stay valid, and the final pass
fixes the deltas. What must not happen is deleting anything on `D:` because `H:`
appears to have it.

---

## 4. Phase 1 - consume the inputs

| Source | Size | State |
|---|---|---|
| Takeout 2026-09-07, 6 parts | ~290 GB | in progress |
| `from-wd6400` | 17,102 files / 140.6 GB | staged on H:, verified at rest, never ingested |
| `from-lorimer` | 1,525 files / 6.96 GB on H:, **744 still to ingest** | the rest already ingested |
| `from-boogles` | **2,340 files / 31.59 GB** | new 2026-09-07, never ingested |
| `in` / `out` | **5 files / ~0 GB** | not media - resolved, see below |

`in\` and `out\` are **not a source**. Between them they hold five files - two `.csv`
and two `.py` in `in\`, one `.csv` in `out\` - working files left by sessions on other
machines. Nothing to ingest, nothing to mirror. Recorded here only so the next session
does not spend time establishing it a third time.

Two of these are not what their name suggests, and neither should be ingested blind:

- **`from-boogles` is not only photographs.** Its 2,340 files are 1,419 `.JPG` and 487
  `.mp4`, but also **202 `.pdf` and 112 audio files** (`.oga`, `.mp3`). PDFs belong in
  `Archive\`, not the chronology, and the `.oga` files are the WhatsApp voice-note
  signature. Route by type before ingesting, or documents and voice notes land in the
  photo chronology and have to be extracted again later.
- **`from-lorimer` is 1,050 `.png` out of 1,525.** That is the known artefact of a
  transfer list built by extension, which swept up every PNG on the machine - mostly
  software project output, QA screenshots and audit evidence. `machine_triage.py`
  exists precisely for this and should run before the ingest, not after.

Each runs the same loop: batch to local staging, ingest with hash dedup, delete the
batch. Re-running is safe - the ingest is content-addressed and checkpointed per member.

**Takeout carries a specific hazard.** Google Photos returns Storage-saver
re-compressions of media already held at full quality. Measured on part 001: 1,123 files
where Google's copy is *smaller* than the one already held, gaps reaching 66.8x - a
1.4 MB clip against a 90.2 MB original. These are not byte-identical, so hash dedup
correctly calls them new and files them.

The rule: **keep the original - the larger, better copy - and move the degraded
duplicate to `_Review\`. Never delete. Where a file is unusually large, flag it rather
than deciding.** The 29 cases where Google's copy is *larger* are the opposite case and
are worth keeping: that is exactly how the full 323.8 MB `20240808_172820.mp4` was
recovered from a library holding only a 15.9 MB truncation.

Because new material lands in `Library\` and not in the chronology, none of this touches
`Personal\` until the split - which is what makes it fixable.

---

## 5. Phase 2 - segmentation

Nothing here is new; it is the existing toolkit applied to everything Phase 1 added.

- `propose_split.py` / `apply_split.py` - assign Personal or Communal **by origin
  folder**, so a few hundred judgements cover tens of thousands of files
- `classify_screenshots.py` - move not-a-memory into `_Review\`
- `move_identity_docs.py` - identity, financial and medical documents into `Archive\`
- `to_content_production.py` - produced content out of the chronology
- `redate_videos.py` - container clock beats folder name

A classifier may **move** a file. It may never delete one.

---

## 6. Phase 3 audit, and Phase 4 the breakout session

The audit is mechanical: `audit_previous_session.py`, `check_manifest.py`, `refresh.py`.
It answers *is the library internally consistent?*

It cannot answer *is this actually my life, filed sensibly?* Only the human can, and
that is the breakout session. **It belongs after segmentation and before the mirror**,
because that is the last moment changes are cheap: a folder moved on `D:` costs seconds;
the same move after mirroring costs a re-upload and a re-verification.

To be worth doing it needs to be queryable, not a folder tree to scroll:

- **Where is X?** - search by year, origin device, folder, filename, size
- **What is in `_Review\`?** - 10,540 files classified as not-memories, grouped by why
- **Where did this come from?** - the origin map already traces every file to its source
- **What is in `Archive\99-Unsorted\`?** - the deliberate pressure valve, reviewed on purpose
- **Show me the biggest things** - where the 563 GB actually is

**This tooling stays local.** The repo is public and the standing decision is that the
folder-level origin map is published while **the per-file map stays on the machine** -
filenames leak. A browsable index of 78,311 personal files is exactly the per-file map,
so it is generated to a local HTML report and never published.

The output is a list of corrections, applied on `D:`, after which the audit re-runs.
**The mirror does not start until the human has said the library makes sense.**

---

## 7. Phase 5 mirror, and Phase 6 prove it

Mirror `PhotoLibrary\`, `Archive\` and `ContentProduction\` - **not the whole drive**,
or the hardlinked bytes upload twice.

Batched, with `C:` checked between batches, and the DriveFS `operations` queue watched
until it drains to 0. A finished copy command is not a finished upload.

Then prove it, the hard way:

1. Generate a manifest on `D:`: relative path, size, whole-file hash.
2. Generate the same for `H:` - **read back through the cloud's own API, not through the
   mount.** Reading the mount reads the local cache, which is the same bytes just
   written; the check and the thing being checked would be identical by construction.
   That mistake has already been made here once, on 140.62 GB, where 17,102 of 17,102
   files verified against themselves.
3. Compare. Every difference is either a file that did not arrive or one that arrived
   corrupted. Neither shows up in a file count.

Only when the manifests match is `H:` a second copy. Until then it is an upload in
progress.

---

## 8. Rules that bind

- **Nothing is deleted on either side because the other side appears to have it.** Only
  a verified content hash justifies a deletion, and the deletion is journalled.
- **The mount is not the cloud.** Free space, file contents and sync state all lie.
- **Never hash off the Drive mount.** Copy local, then hash.
- **A protective copy is not the mirror.** Do not let one quietly become the other.
- **Source material is retired, not mirrored.** Once `from-wd6400` is ingested and the
  library is verified on both sides it has served its purpose - but it is retired only
  *after* that verification, never before.

---

## 9. Open questions

1. **Real quota on the H: account.** The whole plan is capacity-gated and the mount
   cannot tell us. Needs one look at the Drive account.
2. **What are `in\` and `out\`?** Two folders in `_photo-consolidation` whose purpose is
   recorded nowhere in this repo. Establish before touching.
3. **`from-boogles`** - new since 2026-09-07, contents unknown, currently sizing.
4. **Where on `H:` does the mirror live?** NOT a new root folder. The mind/make OS
   architecture reference sets a **hard rule: never create a file in Drive root**, and
   defines exactly ten permitted folders (Agent Briefs, Infrastructure, Client Work,
   Mindmake Strategy, Content, Prospecting, Reports, Career, Signal Inbox, Signal
   Processed). **None of them is for personal media**, and the existing
   `_photo-consolidation\` sits in Drive root already, in breach of that rule.

   So this needs a decision rather than an invention. Either the personal library gets
   an explicitly sanctioned home outside the OS hierarchy - and the OS doc records the
   exception so a future sweep does not "tidy" it away - or it moves under an existing
   folder, none of which fits well. Do not silently add an eleventh root folder: the
   OS has automated diagnostics that key off that structure.
