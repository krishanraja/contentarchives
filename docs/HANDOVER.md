# Handover — consolidation in progress

Enough for another session, or another person, to pick this up without re-deriving
anything. Figures are counted from artefacts on disk by `track.py`, not asserted
from memory.

**This repo is the canon.** Read `state/STATE.json` before anything here — it is
generated, so it cannot have drifted. [ARCHITECTURE.md](ARCHITECTURE.md) has the
storage model and the read/write protocol for sessions.

    python tools/track.py            # recount state from disk
    python tools/publish_state.py    # redact it and update state/

**Last verified:** 2026-09-06

**How it got here, from the commits.** On 2026-09-06 the toolkit was extracted from a
live consolidation together with the learnings that produced it, and the same day the
repo was made the canon: state generated from disk by `track.py` and committed, an
origin map so that batches could be chosen by folder rather than by file, and a
tripwire that refuses to publish anything still resembling identity, medical or
financial material. Later on 2026-09-06 the chronology was split into Personal and
Communal by origin folder, the archive was split the same way, and `RESUME.md` was
added as the front door and then rewritten the same night because it still described a
staging folder hours after that folder had been emptied. On 2026-09-07 the WD6400
rescue was recorded in `docs/rescues/` with rules 22 to 25 paid for on that drive, and
its reusable lessons were folded into `ORGANISING.md` and `ARCHITECTURE.md`. Also on
2026-09-07 a fresh Takeout export showed that part numbers are not stable identities
(rule 26), the `D:` to `H:` mirror was planned in `MIRROR.md`, and the machine-hygiene
runbook arrived with the finding that DISM's CheckHealth and RestoreHealth both
misreport component-store health. Late on 2026-09-07 all six parts of the fresh Takeout
export were ingested and proven, each archive deleted only after its central directory
had been matched against the per-member checkpoint, and `SEGMENTATION.md` recorded the
next checkpoint. At `ee3b550` the generated `state/STATE.json` (2026-09-07T19:14:52)
counts 90,408 files in the library, 60,397 added and 10,026 duplicates rejected on
content hash; the tables below were verified on 2026-09-06 and are older than that state
file, so read it first.

On 2026-09-08 the library was restructured to a single root, `D:\ContentLibrary`, with
`Media\{Personal,Communal,NoDate,Pending-Segmentation}` holding the chronology and
`Archive\`, `ContentProduction\`, `_Review\` and `_Catalog\` beside it rather than
inside it (`d5470d7`). 81,306 files moved by directory rename; `scripts/paths.py` became
the single source of truth after `D:\PhotoLibrary` was found hardcoded 85 times across
40 scripts; and 18,552 files (3,022 screenshots, 2,084 web-asset PNGs, 13,446 received
WhatsApp files) were evicted from the chronology into `_Review`, not deleted. The same
day a second coverage bug was found: the dedup index had covered only `Library\` and
`NoDate\`, 12% of the library, so every one of the 21,649 duplicate pairs found so far
had compared a staged copy against a settled copy it could not see (`e4812dc`). Also on
2026-09-08, the enrichment engine (`engine/`, see `engine/README.md`) was added to work
through `_Review` with metadata, a cheap vision model, then a human (`1a6a2ed`), and
`AGENTS.md` arrived carrying the fleet's shared canon block rendered from
`krishanraja/ai-harness` (`ed45d5e`). A vision pass over 15,689 `_Review` files then
found 10,004 were real memories the sweep rules had missed, mostly received WhatsApp
photographs that metadata could not tell apart from received junk (`8f05203`). On
2026-09-09, 9,975 of those were restored to the chronology, with 29 left in `_Review`
because their origin was never journalled (`9d118a1`), and the on-disk inventory was
rebuilt to 68,042 rows after a doubled root was found and fixed (`77d614e`).

The "Library layout" tables below, and the layout diagram in
[ARCHITECTURE.md](ARCHITECTURE.md), describe the tree before this restructure;
`scripts/paths.py` carries the current one and is the one to read.

---

## What has been consolidated

| Source | Files | Size | How |
|---|---|---|---|
| External archive drive (`D:`) | 26,576 | 293.03 GB | hardlinked — same volume, zero extra bytes |
| OneDrive | 18,356 | 130.71 GB | copied, then released back to online-only |
| Google Takeout (Google Photos export) | 8,369 | 49.90 GB | streamed from `.zip`, never fully unpacked |
| Failing external enclosure, rescued | 2,324 | 28.79 GB | copied off before the drive was retired |
| Google Drive (mounted) | 3,879 | 23.36 GB | copied |
| **Total placed** | **59,504** | | 28,900 hardlinks + 30,604 copies |

Library now holds **59,450 files / 525.9 GB** — 55,554 dated into
`Library/YYYY/YYYY-MM/` and 3,896 in `NoDate/`.

**9,644 files were rejected as duplicates on whole-file hash**, not filename.

Machine-readable version: `provenance-summary.json` on the working machine, with
per-source folder breakdowns.

---

## Library layout

```
<library root>/
  Library/YYYY/YYYY-MM/     dated media, 55,554 files
  NoDate/                   date could not be established, 3,896 files — never guessed
  _Catalog/manifest.csv     every file: destination, original source, link|copy
```

`manifest.csv` (59,505 rows) is the provenance record — it maps every library file
back to where it came from. It is **not** in this repo because it contains real
personal paths; it lives with the library.

---

## Hardlinks — important

26,576 files were hardlinked rather than copied, because the library shares a volume
with the source archive. That addressed **293 GB at zero additional cost**.

Consequences anyone touching this must know:

- A hardlink is a **second name for one set of bytes, not a second copy.** It gives
  no redundancy at all.
- Deleting a "source" file frees nothing while the library entry exists.
- Backing up the library tree copies real content, so backing up the library alone is
  sufficient — but back up *only* the library, or that 293 GB uploads twice.

---

## Stage status

| Stage | State |
|---|---|
| Source inventory | done — 87,206 media files found across all sources |
| Date extraction | done — 92.1% dated; the rest in `NoDate` |
| Deduplication | done — 9,013 duplicate groups verified, 458 video groups checked by duration and 8,555 still groups by pixel dimensions, zero mixed different content |
| Library build | done |
| Failing-drive rescue | done — 2,363 files off, all accounted for, drive retired |
| Google Takeout ingest | 3 of 6 archives consumed; 3 downloading |
| Second machine | surveyed; 1,525 non-duplicate candidates transferred, not yet ingested |
| Compression | **abandoned** — see below |
| Origin map | done — every library file traced to its origin folder |
| Backup | **not started** — the library has no second copy |

---

## Library layout as of 2026-09-06

The chronology is split, and documents live outside it entirely.

```
PhotoLibrary/
  Personal/YYYY/YYYY-MM/    56,928
  Communal/YYYY/YYYY-MM/     3,796
  NoDate/                      853
  Library/                     328   origins with no side assigned
  _Review/                  10,540   classified not-a-memory, nothing deleted
Archive/
  Personal/   01-Identity 02-Financial 03-Property 04-Medical 05-Education 06-Work
  Communal/   01-Identity 02-Financial 03-Property
  99-Unsorted/
ContentProduction/              18
```

Rules that produced it are in [ORGANISING.md](ORGANISING.md); the split was decided
per origin folder, never per file.

---

## Origin map — how batches get chosen

Every file in the library is traceable to the folder it came from. `tools/origin_map.py`
reads the ingest manifest and produces two views; the folder view is the one decisions
are made at.

| | rows | where |
|---|---|---|
| per-file map | 59,504 | library machine only — filenames leak, see ARCHITECTURE.md |
| folder view | 637 | [`state/origin-folders.csv`](../state/origin-folders.csv), redacted |

Largest origins, which is where a quarantine pass should start:

| files | GB | source | origin |
|---|---|---|---|
| 13,346 | 128.0 | OneDrive | `Samsung Gallery\DCIM\Camera` |
| 872 | 70.4 | D: | `Laptop 2024 files` |
| 3,794 | 34.7 | D: | `Samsung S9+ Backup - Sep 2020\DCIM\Camera` |
| 2,607 | 20.3 | D: | `Phone backup Jan 22\DCIM\Camera` |
| 2,231 | 11.9 | Drive | `Old Computer\...PERSON-A phone` — communal, not personal |
| 82 | 15.1 | D: | a 2015 ski trip |
| 57 | 19.8 | D: | a 2015 UK trip |

Two things this immediately shows:

- The bulk is a handful of phone-camera dumps. Personal-versus-communal is mostly a
  question of *whose phone*, and the folder names answer it.
- **34 files are identity or financial documents** — passports, OCI cards, visas,
  birth certificates — swept in from `Downloads` and `Documents` folders. Listed in
  `SENSITIVE-FILES.csv` on the library machine. They should leave the photo library.

---

## Compression: attempted, measured, abandoned

Worth ~83 GB on paper. Dropped because it cannot be done in reasonable time on this
hardware, and the quality evidence was worse than assumed.

Measured on real footage, HEVC, scored against source:

| Source | CRF | Saving | SSIM | VMAF |
|---|---|---|---|---|
| Phone 4K | 22 | 76.7% | 0.9859 | — |
| Sony HD | 16 | 45.0% | 0.9824 | 94.24 |
| GoPro 2.7K | 16 | 37.5% | 0.9760 | **89.83** |
| GoPro 2.7K | 22 | 87.0% | 0.9630 | — |
| DJI 1080p | 22 | 35.0% | 0.9672 | — |

Two findings worth keeping:

1. **Grainy footage has a quality ceiling bitrate cannot raise.** GoPro SSIM moved
   0.0092 across CRF 16→22 while size changed fivefold. VMAF independently agreed at
   89.8, so this is real degradation, not an SSIM artefact.
2. **`libx265 medium` on 4K is impractically slow** — a single 7.21 GB / 20-minute
   file consumed ~2 hours of CPU without finishing. Hardware encode (`hevc_qsv` on
   Intel Iris Xe) exists but still puts 241 files at many hours.

If revisited: use hardware encode, restrict to clean-sensor phone footage, and keep
the per-file gate.

---

## Known outstanding items

In rough priority order:

1. **No backup exists.** The library lives on one external drive that logged 14 disk
   controller errors in a single day. This is the largest open risk. The mirror to
   `H:` is deliberately gated on the audit — see [ARCHITECTURE.md](ARCHITECTURE.md) —
   but that gate is a reason to finish the audit, not a reason to stay unbacked.

   Capacity is not the constraint: `H:` is a 2 TB account with roughly 1.65 TB free,
   against a ~517 GB library. The mount *reports* about 133 GB because it echoes the
   local cache volume — do not plan from that number.
2. **17,101 files / 140.62 GB rescued from the WD6400 childhood-PC drive**, staged at
   `H:\My Drive\_photo-consolidation\from-wd6400\` and awaiting ingest. Verified by
   content hash and confirmed uploaded to the cloud; the source drive can be destroyed.
   Full account in [`rescues/2026-09-06-wd6400.md`](rescues/2026-09-06-wd6400.md).

   Three things the ingest needs to know:
   - Dedupe by the hashes in that folder's `push-manifest.csv` — do not re-read 140 GB.
     The set is already internally deduplicated, but it has **not** been deduped
     against `D:\PhotoLibrary`. Roughly 95 GB matches no size in the library at all;
     ~45 GB shares a size with something held, which is a hint and not a verdict.
   - It is **not all chronology.** It carries tax records, a will allocation document
     and identity paperwork that belong in `Archive`, and it will trip the tripwire —
     see item 6, this is the same class of material.
   - Its folder names actively mislead. `ORGANISING.md` now carries the measured
     examples.

3. **Three Takeout archives** (002/003/004) downloading into `D:\Takeout`; ingest
   resumes automatically per-member when they land.
4. **1,525 files from the second machine** await dedupe and ingest. Their basenames
   were flattened by the transfer (`C_Users_krish_Downloads_foo.mp4`) and must be
   restored from `lorimer-copy-log.csv` before dating, or filename-based dates are
   lost.
5. **`ContentProduction/` is unpopulated.** A TV interview and four large 2026 videos
   belong there, not in the personal library.
6. **34 identity/financial documents** to move out of the library.
7. **3,896 files in `NoDate`** — mostly screenshots and web graphics. Review pass
   deferred until the library is complete.

Free wins already actioned: 8.99 GB reclaimed (a commercial film, and one half of a
re-muxed pair proven identical by duration and creation time), journalled with
evidence to `user-directed-deletions.csv`.

---

## Data loss — read this before changing any exclusion rule

**45 irreplaceable camera-original files, 2.0 GB, were permanently destroyed** during
this consolidation by a path-substring exclusion rule. Full detail in
[LEARNINGS.md](LEARNINGS.md) rules 1 and 2.

Two separate rules caused it: `\Downloads\` matched a phone backup nested inside a
downloads folder, and a folder named `Movies` was assumed to be ripped films but also
held camcorder originals.

`contentarchives/safety.py` exists to make that class of error impossible. Deletion is
allowlist-only, and camera-original filenames are protected unconditionally. Two tests
in `tests/` encode the exact scenarios. **If those tests fail, the toolkit has
regressed into a state that previously lost data.**

---

## Working artefacts (on the consolidation machine, not in this repo)

| File | What it is |
|---|---|
| `STATE.json` / `PROGRESS.md` | current state, regenerated from disk by `track.py` |
| `manifest.csv` | every library file → its original source |
| `inventory.csv` | the original full scan |
| `duplicates.csv` | duplicate groups with the kept copy marked |
| `autopilot-duplicates.csv` | archive members rejected, with the library file matched |
| `PERSONAL-losses.csv` | the 50 unrecoverable files, itemised |
| `E-DRIVE-CONTENTS-AND-WHERE-THEY-ARE-NOW.csv` | rescued drive, per-file accounting |
| `lib-hashes.csv` | persistent whole-file hash cache |
| `arc-progress/` | per-archive member checkpoints |
| `ORIGIN-MAP.csv` | per-file origin map, 59,504 rows |
| `SENSITIVE-FILES.csv` | the 34 document-like files flagged by the tripwire |
| `redaction-key.json` | reverses the pseudonyms in `state/` |
| `user-directed-deletions.csv` | every user-directed deletion, with its evidence |

These stay local because they contain real paths. Anyone continuing should read
`STATE.json` first — it is generated from the artefacts, so it cannot drift from
reality the way a written summary can.
