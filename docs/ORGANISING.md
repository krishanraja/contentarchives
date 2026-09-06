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

```
Archive\
  01-Identity\        passports, visas, residency, birth and marriage certificates,
                      citizenship, national IDs, driving licences
  02-Financial\       tax returns, payslips, banking, investments, insurance
  03-Property\        mortgage, tenancy, deeds, utilities, home documents
  04-Medical\         records, results, prescriptions, correspondence
  05-Education\       transcripts, degree certificates, course material
  06-Work\<era>\      one folder per employer or period: own output, mail archives
  07-Personal-Admin\  correspondence, subscriptions, warranties, official misc
  08-Music\
  09-Reference\       material kept to read or watch later
  99-Unsorted\        awaiting classification
```

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
2. **Take tier D and E first.** No judgement needed, and it frees working space.
3. **Find what is already safe.** Files whose content is byte-identical to something
   already in the library can go — proven by whole-file hash, never by name or size.
4. **Ingest the media** into the chronology, deduped and dated, splitting personal
   from communal by origin folder. Same volume means hardlinks, which cost nothing.
5. **Classify the chronology** into memory / review / uncertain. Move, never delete.
6. **File the rest** into the archive schema.
7. **Regenerate and commit state.** `tools/refresh.py`, then
   `tools/check_manifest.py` to prove every recorded file still exists.

### Rules that apply throughout

- **Move, do not copy-and-delete**, within a volume. It is instant, it cannot half-finish,
  and it does not need free space. Journal every move so it is reversible.
- **Journal every deletion** with its path, size, reason and evidence.
- **A path is never sufficient grounds to delete.** See `LEARNINGS.md` rule 1; that
  rule was paid for with 45 irreplaceable files.
- **Verify by content.** Sizes and filenames are filters that make hashing cheap. They
  are never the verdict.

---

## What this does not cover

This is for **personal** drives and accounts. Shared or communal archives — a family
photo collection, a jointly owned drive — follow the same schema but the retention
decisions are not yours alone to make. Keep them physically separate from the start,
which is what the two-chronology split exists for.
