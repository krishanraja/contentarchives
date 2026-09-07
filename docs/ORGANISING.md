# Organising a personal drive

How to take a drive full of accumulated life — laptop backups, phone dumps, cloud
exports, downloads folders a decade deep — and end up with two things: a chronology
you would actually browse, and an archive you can find anything in.

This is written to be applied repeatedly: to each machine, each external drive, and
each cloud account in turn. Apply it progressively, one source at a time. Nothing
here assumes a particular drive letter or a single run.

---

## The two-tier model

```
  <root>\
    PhotoLibrary\      a chronological memory vault - photos and video only
    ContentProduction\ produced output, kept outside the chronology
    Archive\           everything else worth keeping, by category
    _Working\          scratch and staging, always safe to delete
```

**The chronology is a vault, not a dumping ground.** Its only job is to answer "what
was happening in my life around then". Every file that is not a memory makes it worse
at that job. A screenshot of a train time in `2024-03` is not a memory of March 2024.

**The archive is everything else worth keeping.** Documents, records, work, music. It
is organised by *what a thing is*, not by when it arrived, because that is how you
look for it.

The line between them is not file type. A scanned photograph of your grandparents is
chronology; a scanned passport is archive. Both are JPEGs.

---

## Two chronologies, from the start

```
PhotoLibrary\
  Personal\YYYY\YYYY-MM\      your own life
  Communal\YYYY\YYYY-MM\      family and shared material
  NoDate\                     date could not be established - never guessed
  _Review\                    classified as probably-not-memory, awaiting a person
  _Catalog\manifest.csv       every file mapped to where it came from
```

**Split early.** Personal and communal material arrives mixed and gets more mixed with
every ingest. Once a shared family archive, a partner's phone backup and your own
camera roll are interleaved across the same month folders, separating them means
per-file judgement over tens of thousands of files. Separating them at ingest means
judging a few hundred *origin folders*.

**Split by origin, not by content.** The folder a file came from is strong evidence
and cheap to check: a family member's phone backup is communal, your own camera roll
is personal, a shared holiday album is communal. Guessing from the image itself is
expensive and unreliable. Keep a per-file origin map (`tools/origin_map.py`) and the
split becomes a decision about folders, made once.

Where an origin genuinely contains both, it goes to whichever side dominates and the
exceptions get moved individually. Do not build a third bucket for "mixed" — it
becomes the biggest one and nobody ever empties it.

**But note precisely what the origin folder is evidence *of*.** It is strong evidence
for *whose* material this is — that is the split above, and it holds up. It is weak
evidence for *what the material is*, and treating it as both is how a name-based
triage destroys things.

Phone-dump folders are routinely named after whatever prompted the dump, not after
what is in them. Measured on one drive:

| Folder name says | Folder actually holds |
|---|---|
| `2019-07-23 Anya oci address page 3` | 953 files / **4.74 GB** of phone camera photos |
| `2019-06-24 discharge letter june 2019\Camera` | 63 camera files |
| `2019-07-22 sick note july aug2019\Camera` | 85 camera files |

Someone photographed one document, then emptied the whole camera roll into a folder
named after it. Sorted by name, that is gigabytes of family photographs filed as
medical paperwork — or excluded as documents and never seen again. Sorted by origin
for the personal/communal split, it is correct.

Use the origin folder for *whose*. Use content — EXIF, dimensions, decode — for
*what*.

---

## What belongs in a chronology

**In:** photographs and video that plausibly capture lived experience — camera and
phone originals, scans of old family photographs, messenger media showing people,
places or events.

**Out:** everything below. None of it is deleted by being out; it moves to `Archive`
or `_Review`.

### Screenshots are the single biggest contaminant

Most people take far more screenshots than photographs, and every one of them has a
timestamp that files perfectly into a chronology. They are the largest source of
non-memories in a personal library by a wide margin, and they are easy to detect:

| Signal | Detail |
|---|---|
| **Filename** | `Screenshot_20240312-101533_Chrome.jpg`, `Screenshot 2026-06-26 164307.png`, `Screen Shot 2019-…`, `image.png`, `unnamed.png` |
| **Exact screen dimensions** | a screenshot matches the device's resolution *exactly* — 1080×2400, 1440×3200, 1179×2556, 1920×1080, 2560×1440, 3024×1964. A photograph almost never does |
| **No camera EXIF** | no `Make`/`Model` tag. Cameras and phones always write one |
| **PNG from a phone** | phone cameras produce JPEG or HEIC. A PNG off a phone is a screenshot or a download |

Any two of those together is enough to move a file to `_Review`. Filename alone is
enough when it literally begins with `Screenshot`.

### The rest of what does not belong

- **Documents and scans** — passports, visas, certificates, letters, forms, tickets,
  boarding passes. These go to `Archive`, filed by what they are.
- **Web and app graphics** — icons, logos, banners, avatars, stickers, emoji, cached
  images. Detectable by extreme aspect ratios, tiny pixel dimensions, and living
  under `AppData`, `.cache`, `node_modules`, `assets` or similar.
- **Memes and forwards** — heavy in messenger folders. Text-dominated images, often
  re-compressed several times, frequently at odd dimensions.
- **Product and marketing images** — saved from shopping and listings.
- **Ripped or downloaded commercial media** — films, TV, music videos, YouTube saves.
- **Development and work output** — QA screenshots, prerendered UI, design exports,
  build artefacts. A developer's machine holds thousands.

### Classifying at scale, without losing anything

Tens of thousands of files cannot be reviewed by hand, and a classifier will be
wrong sometimes. So the rule is:

> **A classifier may move a file. It may never delete one.**

Sort into three buckets and treat them differently:

| Bucket | Test | Action |
|---|---|---|
| confident memory | camera EXIF present, or camera-original filename | stays in the chronology |
| confident non-memory | two or more non-memory signals agree | moves to `_Review` |
| uncertain | anything else | **stays in the chronology** |

Uncertain files stay in, deliberately. A false positive costs a moment of noise while
browsing. A false negative costs a memory. Those are not symmetric, and the whole
design should lean the cheap way.

**One caveat that bites:** messenger platforms strip EXIF. WhatsApp media has no
camera tags at all, so the strongest signal is simply unavailable for what is often
the largest group of files. Rely on dimensions and ratio there, and set the bar for
"confident non-memory" higher, not lower.

---

## The archive schema

**The archive splits Personal and Communal too.** Documents are not only your own:
a parent's passport scan, a sibling's residency paperwork, a death certificate.
Those are precisely what you would want to hand over, or hold back, as a batch —
the same reason the chronology splits. Filed together, separating them later means
per-file judgement over other people's records.

```
Archive\
  Personal\
    01-Identity\        passports, visas, residency, birth and marriage
                        certificates, citizenship, national IDs, licences
    02-Financial\       tax returns, payslips, banking, investments, insurance
    03-Property\        mortgage, tenancy, deeds, utilities
    04-Medical\         records, results, prescriptions, correspondence
    05-Education\       transcripts, degree certificates, course material
    06-Work\<era>\      one folder per employer or period: own output, mail
    07-Personal-Admin\  correspondence, subscriptions, warranties, official misc
    08-Music\
    09-Reference\       material kept to read or watch later
  Communal\
    01-Identity\ ...    the same categories, for other people's records
  99-Unsorted\          side or category not established
```

Work sits *inside* `Personal\` rather than beside it. Work output is unambiguously
yours, and leaving it at the top level makes the two sides look like they do not
cover everything — which invites the next person to add a third.

**Numbered on purpose.** It fixes the order to something meaningful instead of
alphabetical accident, and the numbers survive renaming.

**`99-Unsorted` is permanent and should never be empty.** It is the pressure valve.
Without it, every ambiguous file gets forced into a category that is slightly wrong,
and the schema quietly stops being trustworthy. A file sitting in `99-Unsorted` is
honest; the same file misfiled under `07-Personal-Admin` is a lie you will believe
later.

**Identity documents belong here, not in the chronology.** They are dated, they are
scans, and they will file themselves neatly into month folders if you let them. They
are also the most sensitive material on the drive — worth knowing exactly where they
are, and worth thinking twice before syncing anywhere.

---

## The retention rubric

| Tier | Rule | Examples |
|---|---|---|
| **A** | Irreplaceable — keep forever, back up | personal media, own creative work, identity documents, medical records, education certificates |
| **B** | Obligation — keep to a deadline | tax records (7 years in most jurisdictions), employment records, warranties |
| **C** | Replaceable but costly — keep while cheap | music, mail archives, reference material |
| **D** | Regenerable exactly — delete | installers, ISOs, game libraries, OS images, package caches |
| **E** | Never had value — delete | app cache, thumbnails, browser cache, ripped commercial media, `node_modules` |

**Work material:** keep what you authored — decks, documents, published output — plus
mail archives. Drop what you received: vendor material, downloaded reports, corporate
documents that exist elsewhere. This is usually the largest single reduction on a
work-machine backup.

D and E are the safe, large wins and should be done first: they need no judgement and
they buy the space to work in.

---

## Applying this to a new drive

1. **Audit before touching anything.** Walk the volume counting *inodes*, not names.
   Hardlinked files appear twice and are not duplicates — `tools/space_audit.py`
   splits bytes into library-only, hardlinked, and genuinely freeable.

   **Reconcile the audit against the volume's used bytes before believing it.** On an
   old drive, a folder you are denied access to enumerates as *empty*, not as an
   error, so a scan can return "0 files" for the region holding everything. The disk
   said 388.9 GB used while the scan found almost nothing, and the drive was written
   off as corrupt on that basis. It was healthy. The cause was NTFS permissions owned
   by accounts on a machine that no longer exists.

   The fix is an elevated session plus backup-mode reads (`robocopy /B`, which uses
   `SeBackupPrivilege` to bypass ACLs and writes nothing). **Not `takeown /R`** — that
   rewrites security descriptors across the whole MFT of the disk you are trying to
   rescue, which is hundreds of thousands of writes to failing-age hardware.

   Any large gap between "bytes used" and "bytes found" is a permissions problem or a
   container (below) until proven otherwise. It is never an empty disk.

2. **Open any backup containers before deciding what the drive holds.** Old family
   machines commonly carry a proprietary backup set — Norton 360, Acronis, Windows
   Backup, Time Machine — and it can be most of the disk. On the drive above it was
   208 GB of 389 GB, and it was invisible to every media scan because none of the
   files had media extensions.

   These formats are usually far simpler than they look: a short header naming the
   original path, then the original file stored verbatim, uncompressed and
   unencrypted. Read one in a hex viewer before assuming you need the vendor's
   software.

   Two things to plan for, both of which have bitten:

   - **A backup set holds multiple generations of the same original path.** Extracting
     them keyed on that path collapses every generation onto one destination, last
     writer wins, in silence. Give each generation its own destination and collapse by
     content hash afterwards. See `LEARNINGS.md` rule 23.
   - **A container can be a header with no payload** — a filename recorded for a file
     whose contents were never stored. Extracted naively, that writes a zero-byte file
     over a perfectly good copy. 29 family photographs were destroyed this way.

   Contents of a backup set are not automatically redundant with the live filesystem,
   even where the path and size match exactly. See rule 24.
3. **Take tier D and E first.** No judgement needed, and it frees working space.
4. **Find what is already safe.** Files whose content is byte-identical to something
   already in the library can go — proven by whole-file hash, never by name or size.
5. **Ingest the media** into the chronology, deduped and dated, splitting personal
   from communal by origin folder. Same volume means hardlinks, which cost nothing.
6. **Classify the chronology** into memory / review / uncertain. Move, never delete.
7. **File the rest** into the archive schema.
8. **Regenerate and commit state.** `tools/refresh.py`, then
   `tools/check_manifest.py` to prove every recorded file still exists.

### Rules that apply throughout

- **Move, do not copy-and-delete**, within a volume. It is instant, it cannot half-finish,
  and it does not need free space. Journal every move so it is reversible.
- **Journal every deletion** with its path, size, reason and evidence.
- **A path is never sufficient grounds to delete.** See `LEARNINGS.md` rule 1; that
  rule was paid for with 45 irreplaceable files.
- **Verify by content.** Sizes and filenames are filters that make hashing cheap. They
  are never the verdict.
- **Equal size is not equal content.** Rule 7 uses size to rule a duplicate *out*,
  which is free and sound. The converse does not follow, and fixed-size formats make
  the collision ordinary rather than exotic — two generations of a legacy `.xls` will
  differ in content at an identical byte count, because editing a cell does not change
  the file's length. See rule 22.
- **Prove the destination map is injective before writing.** If two sources can resolve
  to one destination, one silently overwrites the other and the job still reports zero
  failures, because every write did succeed. See rule 23.

### When the source will not survive the process

Everything above assumes the original stays where it is. Sometimes it does not — a
drive being destroyed, a machine being wiped, a cloud account being closed. That
inverts the safety asymmetry the rest of this document is built on, and it needs
saying explicitly because the change is easy to miss:

> **Once the source is going away, declining to copy IS deleting.**

Consequences worth planning for:

- **A skip needs the same proof as a delete.** Filters that are merely optimisations
  become irreversible decisions. On one rescue, 19,209 files were skipped because
  their path and size matched something already being copied; hashing them found 174
  where that was false. See rule 24.
- **Copy anything not *proven* duplicate, and dedupe afterwards.** The library's ingest
  already rejects true duplicates on content hash, so let the verdict happen after the
  irreversible step rather than before it. Bandwidth is cheap; the file is not.
- **Verify the keeper set somewhere else, by content, before destroying anything** —
  and if the destination is a cloud mount, confirm it reached the *cloud* rather than
  the mount. See `ARCHITECTURE.md`, and rule 25.
- **Publish one file per distinct content, not one per path.** Build the publish tree
  from hardlinks into the staging tree: same volume, so it costs no space and takes
  seconds. Record which duplicate paths collapsed into each survivor, so nothing is
  discarded unaccounted for.
- **Ship the provenance with the data.** A future session sorting the material will
  have none of the context that made the decisions obvious. Write down where it came
  from, what was excluded and why, what is known-imperfect but kept anyway, and what
  was permanently lost. A per-file manifest with hashes and original paths costs
  nothing to produce and is the difference between an archive and a pile.

`docs/rescues/` holds worked examples.

---

## What this does not cover

This is for **personal** drives and accounts. Shared or communal archives — a family
photo collection, a jointly owned drive — follow the same schema but the retention
decisions are not yours alone to make. Keep them physically separate from the start,
which is what the two-chronology split exists for.
