# Roadmap: from here to two verified libraries and an app that answers a sentence

Rewritten 2026-09-18 from measurement, replacing the 2026-09-11 version whose
phases 1 and 2 were described as "running" a week after they finished. **Every
figure below was counted tonight, from disk or from the rebuilt index, and the
command that produced it is named.** Where something is unknown it says so
rather than estimating.

Krish's goal, in his words: *"two full identical clean content libraries with
the richest possible and most accurate knowledge about the content, such that we
can build a mini app that a user can ask for whoever or whatever they want in
descriptive form, and the webapp will bring them a carousel of content to enjoy,
streamed from the cloud library"* - and, immediately ahead of that, **10 old
communal phones, photographs of old family albums, and VHS conversions** to
ingest over the coming weeks.

---

## Where this actually is

**The library.** `D:\ContentLibrary`, **82,106 files / 925.4 GB** on disk;
82,112 rows in the index (six paths are hardlink siblings). Media 887.1 GB,
ContentProduction 27.3 GB, Archive 9.6 GB, `_Review` 1.3 GB.

**What is known about it.** Rebuilt 2026-09-18 in 141 s:

| field | coverage | field | coverage |
|---|---|---|---|
| `side`, `audience` | **100%** | `place` | 52.7% |
| `kind`, `subject`, `sensitivity`, `setting`, `era` | **99.4%** | `date_taken` | 59.8% |
| `description`, `activity`, `occasion`, `mood` | **99.3%** | `lat` | 42.3% |
| `objects` | 99.1% | `country` / `region` | 41.5% / 41.3% |
| `year` | 85.5% | `text` (OCR) | 36.6% |
| | | `person` | 30.9% |

**Faces.** 48,977 hashes examined, **0 owed**. 119,830 clustered face rows,
1,609 human answers in the journal, 45,807 person-on-photograph rows. The
classifier's people-count filter was measured, not assumed: of 300 sampled
photographs it calls empty, 4 held any face and 2 a confident one (0.7%), and
both of those were faces on a television screen.

**Search already exists.** `library.db` carries an FTS5 table over **15
columns** - `path, subject, place, region, country, person, event, kind, era,
description, objects, activity, text, occasion, mood` - with a porter stemmer.
`python stages/08_index/build_db.py --ask "beach"` proves it. A descriptive
query has real prose to match against, not four-word labels. **This is the app's
backend, and it is built.**

**The intimate content is destroyed** (2026-09-18, at Krish's instruction): 81
files purged, 7 he had already removed, 88 hashes blocklisted, every derived
trace swept and verified at 0. See `stages/10_reclaim/purge_content.py`.

### The three things that are NOT what the old roadmap assumed

1. **`E:\ContentLibrary` is not a mirror. It is the stale predecessor.** 73,198
   files / 844.1 GB, newest write 2026-09-11, and it has **no `Intimate`
   folder**, so it predates the sweep. It is 8,908 files and 81 GB short of the
   live library. Treat it as 844 GB of reclaimable space holding one useful
   thing: a last-resort copy of pre-purge state, which is now a reason to clear
   it deliberately rather than keep it by accident.
2. **G: and H: are two DIFFERENT Google accounts** - `krishanraja@gmail.com`
   and `krish@themindmaker.ai`. Both hold `_photo-consolidation` *source*
   folders (H: alone: 24,901 files / 501.5 GB). Neither holds a library copy.
3. **The cloud target is H:, it has 2 TB, and the library fits today.** Krish
   confirmed the quota on 2026-09-18; it is **not locally verifiable** - the
   mounts report their local cache volumes (learning 17, H: claims 475.6 GB),
   DriveFS's `metadata_sqlite_db` carries no quota table in either account, and
   `gcloud auth print-access-token` returns `invalid_grant`. Recorded as his
   figure, with that caveat, rather than as a measurement.

   Measured here from the mount's metadata (no placeholder hydrated):

   | | GB |
   |---|---|
   | quota (Krish, 2026-09-18) | 2,048.0 |
   | stored now, 32,606 files across 25 folders | 537.6 |
   | **free** | **1,510.4** |
   | the library | 925.4 |
   | spare after upload, clearing nothing | **585.0** |
   | spare if `_photo-consolidation` is cleared first | 1,086.5 |

   Access is proven in both directions: 24,902 files enumerated, and one file
   deleted from the mount and confirmed gone.

---

## Phase A - make the engine safe to leave alone  ·  ~1 day  ·  free

Everything after this is bulk work, and bulk work is where unattended machinery
either earns its keep or quietly loses things. Ten phones, album photographs and
VHS captures arriving over weeks is exactly the load that found every bug below.

**A1. The blocklist is LIVE. DONE 2026-09-18.** `autopilot.blocked_index()`
loads `PURGED-HASHES.csv` into `{size: {hashes}}` once, and `is_blocked()`
refuses a purged hash by CONTENT in `ingest_folder` (after the `size == 0`
guard) and in `ingest_archive` (after the member is streamed out, because there
is no file to hash before that). Every refusal is journalled to
`D:\_PhotoAudit\autopilot-blocked.csv` with the hash and the source - a file
that silently vanishes mid-ingest is indistinguishable from a bug. The size
gates the hash, so 88 files cost no throughput: a candidate whose size is not
blocked is admitted without being read. Pinned by `tests/test_blocklist_hook.py`
(22 checks), which proves the size gate by making `full_hash` RAISE.

**All four ingest paths are covered, and only two hooks were needed.**
`autopilot.py` and `ingest_tree.py` call `is_blocked` directly. The other two
delegate: `ingest_from_h.py` copies a batch into `P.H_STAGE` and then runs
`ingest_tree.py --apply` on each routed subfolder by subprocess, and
`extract_zip_media.py` extracts to `D:\_zip_extract` and hands its personal side
to the same tool. So nothing reaches the library without passing the gate.

Checking that was the point. The first version of this note said three paths
were unhooked and told the next session to route phones through `autopilot.py` -
advice that would have been wrong in the other direction, because
`ingest_tree.py` is the documented tool for a phone and is now the better path.
Delegation is coverage, but only once you have read the delegation.

**The residual, stated precisely:** blocked bytes can still be COPIED INTO A
STAGING FOLDER before being refused - `P.H_STAGE`, `D:\_zip_extract`, and
`D:\_Staging\from-old-zips\work` for the work side, which is not ingested at all
and is left for a human. They never enter the library, and `ingest_from_h`
rmtree's its stage after each batch, but a purged file can exist on disk for the
length of one batch. Hooking the copy loops as well would stop that; it needs
the hash before the copy, which on a Drive mount means hydrating the file to
read it, so it is not free.

While wiring it up, the blocklist itself turned out to hold seven rows with a
SIZE in the `Hash` column, written by `drop_removed_rows.py` (learning 60).
`blocked_index()` therefore ignores and COUNTS any row without a 64-hex hash
rather than trusting the file it reads.

**A2. `--traces-only` exists. DONE 2026-09-18.** `purge_content.py
--traces-only --blocklist-also <csv>` sweeps the derived copies of hashes whose
files are already gone, and deletes no files at all. The normal path cannot do
this by design: `verify()` re-hashes every target at the instant of deletion -
the defence that stops a stale list destroying the wrong files - so a vanished
file fails as "already gone" and can never become a target.

It refuses three ways rather than doing something surprising: with `--list`
(which has no meaning when nothing is being deleted), without
`--blocklist-also` (nothing to sweep is not the same as nothing to do), and with
`--also` (which deletes a file, and this mode exists because there is no file
left to verify against). It journals no deletion, because there is none -
writing a header-only record would put an empty entry in the audit trail and
`audit_deletions.py` would count it.

**And the bug found while adding it, which mattered more.** The trace sweep's
COUNTS have always been computed over `sweep` - targets plus block-only hashes -
while the ACTIONS keyed on `targets` alone. So the summary a person approves the
purge from promised 117 tag rows, 5 face vectors and 5 bounding boxes, and the
sweep then removed fewer. A report that overstates what was done is worse than
one that understates it, because it is the report the decision is made on. Fixed
at the three action sites: `content_tags.csv`, `zero_face`, `strip_cluster`.
`PATH_RECORDS` correctly still keys on paths, because a block-only hash has no
path to remove.

**A3. Arm the fortnightly ingest.** `guards/arm.ps1`. CronCreate is
session-scoped and expires after 7 days; a scheduled task is not.

**A4. `refresh.py` was calling a script that moved.** Fixed 2026-09-18; it now
resolves repo-relative paths and refuses a missing step loudly. Re-run
`python tools/refresh.py` after any session that moves files - `state/` was two
days stale because this failed quietly.

**A5. Turn on the USN change journal.** `fsutil usn createjournal m=32M a=8M D:`
On 2026-09-18 seven files vanished from the library and **no record of the
deletion existed anywhere** - the journal is not active, Defender logged
nothing, and there is no process attribution on this machine. It turned out to
be Krish himself, but the next time the answer should come from a log rather
than from an investigation.

---

## Phase B - ingest the new material  ·  weeks, as it arrives  ·  free

> **THIS IS NOW THE FRONT LINE (2026-09-20).** Phase A is done: the blocklist is
> live and caught 88 purged files trying to re-enter on its first real use,
> `--traces-only` exists, and `refresh.py` is fixed. The consolidation is
> finished - 81,449 files / 805.1 GB, zero internal duplicates, two verified
> copies, 1,114 GB reclaimed. **Nothing else blocks the new material.**
>
> Three sources are coming: **VHS captures**, **10 old communal phones**, and
> **photographs of old photo albums**. Two of those three carry no EXIF at all,
> which makes the folder name the only date signal they will ever have - so the
> single highest-value thing to do before ingesting anything is to NAME THE
> FOLDERS WITH THEIR YEAR. It costs minutes and it is the difference between a
> dated library and a `NoDate\` pile.

The toolchain for this is the most battle-tested part of the repo. Use it as it
is; do not write a new importer.

| what | tool | why this one |
|---|---|---|
| a phone, a card, a folder | `stages/02_ingest/ingest_tree.py` | dedupes on content, dates from EXIF then name then folder |
| a Takeout or a zip | `autopilot.py` | streams members, per-member checkpoint, survives a kill mid-archive |
| anything unattended | `stages/02_ingest/driver.py` | loops passes and survives the memory watchdog |
| deciding where it lands | `stages/02_ingest/route_h.py` | chronology / production / archive, vocabulary from the profile |
| proving a batch landed | `stages/02_ingest/verify_h_batch.py` | by count AND hash |
| "why is everything new?" | `stages/02_ingest/diagnose_new.py` | the answer is almost always a stale path index |

**Per source, in order:** ingest → `verify_h_batch` → thumbnails
(`backfill_thumbs.py` drives from the index and does not re-walk 82,000 files) →
`classify_live.py --apply` → `--rich` → `faces_embed.py` → `build_db.py` →
`refresh.py`.

**Three things that will bite, all of which already have:**

- **Delete `D:\_PhotoAudit\lib-index.pickle` after anything that moves or
  removes library files.** 62.9% of its cached paths once pointed at files that
  no longer existed, and 222 GB of byte-identical duplicates were admitted
  because a candidate that will not open hashes to `None`, and `None == th` is
  False.
- **VHS captures and album photographs have no EXIF.** They will land in
  `NoDate\` and stay there unless dated by folder name. Name the folders with
  the year *before* ingesting - it is the cheapest date you will ever get.
- **A phone's video may be HEVC, and an album photograph may be a 100-megapixel
  panorama.** `thumbnail.py` now registers `pillow_heif` and sets
  `LOAD_TRUNCATED_IMAGES`; without those, 82 iPhone photographs and 18 damaged
  Samsung panoramas were invisible to every pass at once, because the
  classifier, the descriptions, the face pass and the game all read
  `D:\_thumbs`.

---

## Phase C - segment and enrich what arrives  ·  hours per batch  ·  ~$2 / 2,000 files

`stages/09_segment/propose_split_by_path.py` → `review_split_by_path.py` →
`apply_split_by_path.py`, then re-run the enrichment chain. Krish's rule stands:
anything with `bharti`/`bhasker` in the folder name, or from `Users/Raja`, is
Communal; the rest Personal; **a file already in a Communal folder is never
demoted**; device ownership is device-level, not year-level.

Then the naming game: `stages/07_people/build_game.py --who krish --batch N`,
gated by `verify_people_sheet.py` **and** `check_repeats.py`, published as a
private artifact with `capabilities {db:{}}`, answers back via
`ingest_game_answers.py --apply`. **Bharti's game is still unbuilt** (~31
batches at the 0.12 face-share floor; her answers must carry `who=bharti`).

`person` at 30.9% is the single biggest gap in "richest possible knowledge", and
it is the one only a human can close.

---

## Phase D - the second identical library  ·  ~6-8 h  ·  free

Disk to disk, and this is the cheap half of the goal.

1. **Prove D: is complete first.** `tools/refresh.py`, then
   `python tools/check_manifest.py`, then `sweep_intimate.py --verify`. A mirror
   of an incomplete library is two incomplete libraries.
2. **Clear `E:\ContentLibrary`** - 844 GB of stale predecessor - through
   `guarded_delete.py`, which refuses unless a surviving copy is proven at the
   instant of the unlink. This is what makes room; E: has only 26.9 GB free.
3. **Copy D: → E: hashing in flight**, the way `migrate_library.py` already
   does. Record blake2b per file as it lands. Do not verify by re-reading the
   destination through a filesystem cache.
4. **Verify by comparing recorded hashes**, file for file, count for count.
   `postswap_check.py` exists for exactly the "prove this disk is the library"
   question.

**Done when** both trees have identical file counts, identical total bytes, and
a zero-mismatch hash report. That is two identical clean libraries, locally.

---

## Phase E - the cloud copy, and the one the app streams from  ·  ~30 h  ·  free but slow

**Not blocked on space any more.** The target is **H:**
(`krish@themindmaker.ai`), 2 TB, with 1,510.4 GB free against a 925.4 GB
library - it fits with 585 GB spare before clearing a single source folder.
What is still unmeasured is the upload RATE, and that is the one number this
phase should not assume.

1. **Measure the upload rate properly, before committing to a window.**
   Download was 10.5 MB/s; upload has never been measured here and symmetry is
   learning 10's whole subject. **Timing a copy to H: measures the wrong
   thing** - that write lands in the local DriveFS cache at disk speed and the
   upload happens afterwards, asynchronously. The real rate is the
   `operations` queue draining, which `move_audio_to_h.py:queue_depth` already
   reads from the account that owns the destination. At 10 MB/s a 925 GB
   library is ~26 hours; at 2 MB/s it is 5 days, and that difference decides
   whether this runs overnight or over a week.
2. **Optionally clear the consumed source folders first**
   (`_photo-consolidation`, 501.5 GB / 24,901 files) - now an optimisation
   rather than a gate, and worth doing because it is material already verified
   into the library. Only after `verify_takeout_complete.py` and
   `verify_h_batch.py` confirm every byte is in the library **and on the Phase
   D second copy**. Not "on E:" - E: is the stale predecessor until Phase D
   rebuilds it.
3. **Measure the upload rate before committing to a window.** Download was
   10.5 MB/s; upload has never been measured here and symmetry is an assumption.
4. **Upload computing MD5 in flight.** Drive exposes a server-side
   `md5Checksum` and that is the only verification it offers; our hashes are
   blake2b, so an MD5 must exist locally to compare against. Computing it during
   the upload avoids a second 925 GB read.
5. **Verify against the server-side checksum - never by reading back through
   the mount.** Reading a placeholder hydrates it and fills C: (learning 5); a
   mount read can hang with zero bytes rather than failing (learning 15); and
   learning 25 is a run that "verified" 17,102 of 17,102 files by comparing
   local bytes with local bytes. `move_audio_to_h.py` is the only cloud-verified
   path built here, and its receipt proof - the DriveFS `operations` queue plus
   `cloud_has()` - is the pattern to extend.

**Done when** every row in `MASTER.csv` carries a matching server-side MD5 and
the mismatch count is zero. **Stage 11 currently has no tests and its own
`STAGE.md` says the H: upload "is not built". This phase is where the remaining
engineering actually is.**

---

## Phase F - the app  ·  days, not weeks, because the hard part is done

The backend is `library.db`. The FTS5 table already answers a sentence.

1. **A read-only query API** over `search` joined to `v_files`, returning
   `path, description, date_taken, place, person, audience, hash`. Rank by FTS
   score; `audience` is already on 100% of files and is the access control -
   `family` is shareable, `private` is not.
2. **Serve media from the cloud copy, not from D:** - that is what Phase E is
   for. The `hash` is the stable key; paths move and have moved repeatedly.
3. **The carousel** is thumbnails from `D:\_thumbs` (already 512px,
   content-addressed) with the full file streamed on demand.
4. **What makes it feel good** is `description` + `objects` + `person`, which is
   why Phase C's naming game matters more to the app than any front-end choice.

One warning worth carrying into the app: **a derived copy outlives the original
it came from.** The purge had to sweep thumbnails, sampled frames, face
embeddings, descriptions and index rows, and a first pass missed seven of each
because it keyed on deletable files rather than on blocked content. An app that
caches thumbnails or descriptions anywhere else creates another place a deletion
has to reach.

---

## The order is not arbitrary

- **Phase A before B.** Unattended ingest with an inert blocklist re-admits
  purged content, and a stale path index manufactures duplicates. A1 is done -
  the blocklist is enforced in `autopilot.py` - but three other ingest paths
  still do not call it, so that much of A is not finished.
- **B before C.** Segmentation decides Personal/Communal from enrichment, and
  enrichment needs thumbnails, which need the files.
- **C before D.** Segmentation moves files; a mirror taken first must be
  re-synced, and a cloud re-sync is ~23 hours.
- **D before E.** Two local copies, then the slow one.
- **E before F.** The app streams from the cloud copy.
- **Nothing is deleted from anywhere until two verified copies exist** - and
  "verified" means a hash compared against the destination's own evidence, not a
  copy that returned success.
