# Roadmap: from here to two mirrored libraries and a game that fills the sheet

Specified by Krish on 2026-09-11: two final full libraries mirroring on H: and the
LaCie, enrichment as far as it can go, segmentation off the back of it, Elements purged
once everything is in two places, and `MASTER.csv` wired to a front end that can be
played daily to fill the remaining columns.

**The ordering is not arbitrary.** Three dependencies fix it:

- **Enrich before segmenting.** Segmentation decides Personal vs Communal vs
  not-a-memory, and the enrichment fields are the evidence for that decision.
- **Segment before mirroring.** Segmentation moves files. A mirror taken first has to
  be re-synced afterwards, and a cloud re-sync is ~23 hours.
- **Mirror before purging.** Nothing leaves Elements until the content is verifiably in
  two other places. Not "copied" — verified.

Phases 1 and 2 are running unattended as of 2026-09-11 21:00.

---

## Phase 1 — Finish the ingest  ·  running  ·  ~2.5 h  ·  free

`from-wd6400`, the last source folder: 100.8 GB to pull, 77.9 GB certainly new.

**Done when:** the log shows all 6 batches complete, and `H-COPY-FAILURES.csv` either
does not exist or is empty. If it has rows, those files never reached the library and
nothing else will say so.

---

## Phase 2 — Thumbnails  ·  chained, starts automatically  ·  ~2 h  ·  free

81,364 assets missing: every image at 512px, plus four ffmpeg frames from each of
10,792 videos. Six shards, because this is CPU-bound and workers genuinely help.

**Done when:** `thumbs-chain.log` says DONE and the thumbnail count is near 97,000.
Nothing can be classified without this.

---

## Phase 3 — Enrichment  ·  ~4 h  ·  ~$41

Two jobs, in this order:

1. **Rebuild the technical metadata.** `INVENTORY.csv` is 68,042 rows from before the
   migration, and it feeds eight columns of `MASTER.csv`.
   `python scripts/build_inventory.py --video` — the `--video` flag is slow and is what
   fills `Duration`, `Width` and `Height` for 10,792 videos.
2. **Classify.** `python engine/classify_live.py --thumbs D:\_thumbs --store
   D:\_enrichment --apply`. Gemini 3.1 Flash-Lite, twelve threads, resumable, with
   `--max-usd` stopping on measured spend.

**Done when:** `python tools/master_sheet.py` reports `kind`, `people`, `subject`,
`keep`, `sensitivity`, `setting` and `era` near 100%. Expect overall coverage to go
from **59.2% to roughly 88%**. What remains after this is what no model can supply:
*who* the people are, *which* event a photo belongs to, and dates for undated files.
That residue is the game's job, and it is Phase 8.

---

## Phase 4 — Segmentation  ·  ~1 day, mostly review  ·  free

Now the enrichment exists, the decisions it was blocking can be made. Each one moves
files and each one is journalled and reversible. **Nothing is deleted in this phase.**

1. **Assign a side** to `Media\Pending-Segmentation\` — 6,215 files, 205.6 GB — with
   `propose_split.py` then `apply_split.py`. The split is by origin folder, which is
   the decision already made: a few hundred folder judgements rather than 74,000 file
   ones.
2. **Evict the non-memories** the classifier finds: `kind` in screenshot/meme/graphic,
   or `keep=false`. They go to `_Review\`, never to deletion. Krish empties `_Review`,
   not a script — that rule was paid for when a rules-based sweep evicted 13,446 files
   and a vision pass found 10,004 of them were real memories.
3. **File the five identity documents** out of `Media\NoDate\` into
   `Archive\Personal\01-Identity\` with `move_identity_docs.py` (machine-only script).
4. **Quarantine anything marked `sensitivity: intimate`** per the standing instruction.
   `private-family` stays in the chronology and is never surfaced in the game.
5. **Resolve the two known duplicate sets**: 51 derived copies in
   `DERIVED-IN-CHRONOLOGY.csv`, and 14.88 GB of hash-confirmed cross-tree duplicates in
   `XTREE-DUPLICATES.csv`. Note the fourth pair in that file is NOT a duplicate: same
   name, same exact byte count, different footage. Learning 36.
6. **Attack `NoDate\`** — 2,876 files, 109.8 GB, now the second largest tree. The
   classifier's `era` field is the only date signal these have; it gets them into a
   decade, not a month. Anything better comes from the game.

**Done when:** `Pending-Segmentation` is empty, `_Review` holds only what Krish has
seen, and `MASTER.csv` shows every file with a `Side`.

---

## Phase 5 — Reclaim, before anything is mirrored  ·  ~2 h  ·  free

Deduplicate now, so the cloud upload does not carry redundant bytes at ~23 hours a
copy.

- Reclaim the hash-confirmed duplicates through `guarded_delete.py` — the only
  sanctioned path: different inode, equal size, blake2b re-hashed at the instant of the
  unlink, survivor readable to its last byte.
- Re-run `reclaim_d_originals.py` against the new layout. Remember learning 28: the
  figure that matters is inode-distinct bytes, not what a folder listing claims.

**Done when:** `tools/track.py` shows a library size that will not shrink further, and
that is the number the mirror is sized against.

---

## Phase 6 — The cloud mirror  ·  ~30 h  ·  free but slow

This is the phase with the most unknowns and the one where a shortcut would be worst.
**H: today is the source, not a mirror.** It holds `_photo-consolidation`, the input
folders. There is no library copy on it.

1. **Clear the consumed source folders** from H: — roughly 371 GB, all of it now
   ingested and verified on two local disks. This is what makes room.
2. **Read the real quota from the Drive API.** `Get-Volume` on H: reports the local
   cache volume, not the account (learning 17). The library will be ~900 GB against a
   2 TB account; confirm rather than assume.
3. **Measure the upload rate.** Download measured 10.5 MB/s. Upload has never been
   measured and symmetry is an assumption, which is learning 10's whole subject.
4. **Upload, computing MD5 on the way through.** Drive exposes a server-side
   `md5Checksum` and that is the only verification available; our hashes are blake2b,
   so an MD5 has to exist locally to compare against. Computing it during the upload
   avoids a second 844 GB read, exactly as the migration hashed during the copy. Store
   it as an extra column in `HASH-INDEX.csv`.
5. **Verify by comparing the server-side checksum to the local one.** Never by reading
   files back through the mount: it hangs with zero bytes read rather than failing
   (learning 15), and reading a placeholder hydrates it and fills C: (learning 5).
   Learning 25 is a run that verified 17,102 of 17,102 files against a cloud mount
   having compared local bytes with local bytes — this must not be that.

**Done when:** every file in `MASTER.csv` has a matching server-side MD5 recorded, and
the count of mismatches is zero. **This is the gate for Phase 7 and nothing else is.**

---

## Phase 7 — Purge Elements  ·  ~1 h  ·  frees ~525 GB

Only after Phase 6 verifies. Three things have to be true first, and one of them is
easy to forget:

- **The ~39 GB of sole-copy content on Elements must be ingested first.** Those are
  files in the 20-year folders that exist nowhere else — not in the library, not in the
  cloud. Purging before ingesting them destroys the only copy. Run `ingest_tree` over
  each remaining source folder; media joins the chronology, documents route to
  `Archive\`, and anything already held is recognised and skipped for free.
- **The arithmetic is not what a folder listing says.** Roughly 319 GB of the library is
  hardlinked to originals in those folders, so deleting the library tree frees about
  **525 GB, not 844**. Same illusion as learning 28, pointed the other way.
- **Deletion goes through `guarded_delete.py`.** Every file, no exceptions, with the
  surviving copy re-verified at the instant of the unlink.

**Done when:** Elements holds only what Krish chose to keep, and every byte removed had
two verified survivors at the moment it went.

---

## Phase 8 — The game  ·  ongoing  ·  the point of all of it

`MASTER.csv` reaches roughly 88% on models alone. The last stretch is the part only a
human who was there can supply:

| column | who can fill it |
|---|---|
| `person_id` per face | only Krish — a model can cluster faces, only a human names them |
| event / trip | only Krish |
| date for `NoDate` files | only Krish, from recognising the occasion |
| correcting a wrong `kind` or `keep` | Krish, in seconds, one swipe |

There is a prototype already: `engine/swipe/index.html` and `server.py`, and `store.py`
already carries `people`, `observations` and a merge-suggestion table with the rule that
naming is recorded as a new row rather than an edit, so the history of what someone was
called stays visible.

What it needs to become a daily habit:

1. **Face clustering first**, so the question is "who is this?" once per person rather
   than once per photo. Cluster locally, present the largest clusters first — naming
   twenty clusters can label thousands of images.
2. **A phone-reachable front end.** Krish asked for this in September: *name People by
   face or point out specific things about photos on my mobile.* The images live on a
   local disk, so this is a real design decision and it is **open** — a local server on
   the LAN, or a hosted page with a subset of thumbnails uploaded. ~97,000 thumbnails at
   ~50 KB is ~4.8 GB, which is too much to publish wholesale; a working set is not.
3. **Write-back as `source: human`**, which already outranks every model in
   `master_sheet.py`'s `SOURCE_RANK`. A human answer is never overwritten by a model.
4. **Show the number.** The session ends with the coverage figure and how much today's
   play moved it. That is the whole motivation loop, and it is why `master_sheet.py`
   prints a score rather than a table.

**Done when:** it is worth playing. That is a product judgement, not a checklist.

---

## Open decisions

| decision | why it is open |
|---|---|
| Where the game runs — LAN server or hosted page | the images are on a local disk and ~4.8 GB of thumbnails cannot all be published |
| Whether `_Review` is ever emptied, and by what rule | Krish reviews it; a rule already got this wrong once, at 13,446 files |
| Whether `Archive\` and `ContentProduction\` move inside the media root | decides the root of the mirror (`docs/SEGMENTATION.md` section 3) |
| Whether the 51 derived copies are memories or clutter | some are edits Krish made, not machine transcodes |

## What would make this go wrong

- **Mirroring before segmenting.** Costs a second 23-hour upload.
- **Purging Elements on "it is copied" rather than "it is verified."** One file in
  73,198 copied to the right size with the wrong bytes on 2026-09-11. Only a hash found
  it.
- **Trusting a cloud verification that never left the local disk.** Learning 25.
- **Letting a rule empty `_Review`.** Learning: 10,004 of 15,689 evicted files were
  real memories.
