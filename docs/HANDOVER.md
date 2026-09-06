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
2. **Three Takeout archives** (002/003/004) downloading into `D:\Takeout`; ingest
   resumes automatically per-member when they land.
3. **1,525 files from the second machine** await dedupe and ingest. Their basenames
   were flattened by the transfer (`C_Users_krish_Downloads_foo.mp4`) and must be
   restored from `lorimer-copy-log.csv` before dating, or filename-based dates are
   lost.
4. **`ContentProduction/` is unpopulated.** A TV interview and four large 2026 videos
   belong there, not in the personal library.
5. **34 identity/financial documents** to move out of the library.
6. **3,896 files in `NoDate`** — mostly screenshots and web graphics. Review pass
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
