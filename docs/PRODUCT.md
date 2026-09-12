# What would survive as a product

This repository is two things at once: the record of one person's media
consolidation, and a toolkit that was extracted from it. This document separates
them, because the second is the part with a future and the first is the part
that makes the second credible.

Written 2026-09-12, from a library of 82,194 files across 844 GB, classified end
to end for about $27.

---

## The problem, stated precisely

Metadata takes you a long way and then stops dead. Measured across all 82,635
inventory rows on a real library:

```
Side, kind, bytes, origin join  100%     vision: kind/subject/keep   ~100%
year / month                     85.5%   sensitivity/setting/era     ~100%
origin folder                    84.4%   lat / lon                    33.6%
EXIF date                        46.5%   place name (before geocode)   4.4%
camera make / model              45.8%
```

The gap is not evenly distributed, and that is the whole point:

> `042.jpg` is a toddler in green dinosaur pyjamas being handed a bowl.
> `bharti phone 3034.jpg` is a forwarded flyer with somebody's bank details on
> it.
>
> Both are JPEGs of a couple of hundred KB. Both have no EXIF, because a
> messenger stripped it in transit. **No rule separates them.** A vision model
> separates them instantly, and a human separates the people in them.

So the architecture is forced: cheap signals first, a small vision model for what
they cannot settle, and a human for what neither can — asked as few questions as
possible.

---

## The reusable core

These take every path by argument and carry no knowledge of this library:

| module | what it does | scale proven |
|---|---|---|
| `engine/thumbnail.py` | content-hash-keyed 512px thumbnails, EXIF orientation honoured | 79,020 assets |
| `engine/frames.py` | video keyframes into the same cache | |
| `engine/store.py` | append-only, fsynced tag store keyed on content hash | 446k+ rows |
| `engine/classify_live.py` | vision classification, sharded, resumable, spend-capped | 79,017 files, $27 |
| `engine/faces_embed.py` | face detection + 512-d embeddings, only where a face was reported | 51,797 images |
| `engine/geocode.py` | offline reverse geocoding, no API, no expiry | 170,987 places |
| `engine/answers.py` | append-only journal of human judgements | the irreplaceable one |
| `tools/master_sheet.py` | joins every source into one row per file | 82,635 rows |
| `tools/build_db.py` | SQLite + FTS5, derived rebuilt, asserted preserved | |

**Not portable, and not pretending to be:** `engine/bakeoff.py` and
`engine/consensus.py` hardcode this machine's paths. They are one-off analyses
that chose the model and measured its error rate. They earned their keep and
they are not library code.

---

## The four ideas worth keeping

### 1. Folders stay dumb. Context lives in an index.

A folder hierarchy can express exactly one axis. Every fact encoded in the tree —
person, place, event, topic — is a fact that cannot be cross-cut without
duplicating files, and the urge to encode more is precisely what produces
twelve-deep nesting nobody can navigate.

So the library is chronological and four levels deep, for ever:

```
Library/Media/<side>/<year>/<year-month>/<file>
```

87.4% of this library already sits exactly there. Its only job is that a human
with no tools, on any OS, in twenty years, can find things by date and never
lose them. Everything else — who, where, what, when-really — lives in an index,
and *asking* is a query layer over that index.

### 2. Derived and asserted are different kinds of data

This is the distinction most personal-data tools get wrong, and it is cheap to
get right at the start and expensive to retrofit.

**Derived** — EXIF, hashes, thumbnails, model output, geocoded places, face
clusters. Regenerable. If it burns down, the cost is bounded: time and money.
This library's entire classification can be re-bought for $27.

**Asserted** — what a person decided. *This is who that is. That folder was the
Italy trip. That one is not worth keeping.* It exists nowhere else in the world.
No amount of money or compute reproduces it; it has to be asked again, of a
human who already answered.

So the asserted data is **not a table in the database**. It is an append-only
CSV that the database is built *from*, and no build path can write to it. The
clever, fragile, regenerable thing depends on the dumbest, most portable thing —
a text file any tool on any machine in any decade can read — rather than
containing it.

Corrections append rather than overwrite, so the record answers "when did I
decide that, and what did I think before?"

### 3. Scope answers so one costs thousands

The scarce resource is not storage or compute. It is the person's attention. So
an answer names a **scope**, never a file, wherever it can:

```
cluster   a face cluster    -> every photograph that person appears in
folder    a library folder  -> everything filed under it
origin    a source device   -> everything that came from it
file      one content hash  -> exactly one file
```

This was proved before it was designed. The Personal/Communal split ran at folder
level, and *"74,000 file judgements became a few hundred folder judgements."*
Naming ~50 face clusters is the same trick over the 51,797 images with a face in
them.

Ranking candidate questions by *files labelled per answer* is the scheduler a
gamified enrichment loop should run on.

### 4. Every irreversible act needs a stronger check than every reversible one

Paid for with 22,410 files deleted with no surviving copy, 50 of them personal or
camera-original. The rules that came out of it:

- **A path is never sufficient grounds to delete.** Deletion is allowlist-only.
- **A duplicate may only be declared on a whole-file hash match.** Equal size is
  not equal content — one 7.7 GB file in a 73,198-file migration copied to the
  exact right size with different bytes, and every cheap check passed it.
- **Re-verify the survivor at the instant of the unlink**, not before the batch.
  `guarded_delete.py` re-hashes the surviving copy as each file is removed and
  refuses without one. 442 receipts, 0 refused.
- **A green report is not proof.** A copy job reported "0 failures, and it was
  telling the truth. Every write succeeded" while later writes destroyed earlier
  ones.

---

## The operational lessons, which are most of the real cost

A batch job over a personal archive runs for hours on a machine that is not a
server. Everything below was paid for in lost work, in one week:

- **Checkpoint per unit, not per job.** Append and fsync after each item. A
  killed run must resume, not restart.
- **Resumability is what makes a kill cheap.** Classification died twice at
  53,325 and 14,750 files in. Neither cost anything but minutes, because the
  store is append-per-file and the classifier skips what it has already tagged.
- **"Detached" must be tested, not assumed.** `Start-Process -WindowStyle
  Hidden` hides a window and leaves the process in the caller's tree. It
  survives everything except the one event it was chosen to survive.
- **Stopping a supervisor is not stopping the work.** Unregistering a scheduled
  task kills its shell and orphans its children — an orphaned classifier went on
  spending money against the same work list as its replacement.
- **A brake a retry loop can push through is not a brake.** A per-run spend
  ceiling plus automatic restart is an unbounded budget. Deliberate stops must
  leave a marker that survives the restart.
- **A fallback branch with no failure mode is a silent failure.** `if not
  os.path.exists(FFPROBE): return {}` meant 12,988 videos got no duration for
  33 minutes and the run reported success.
- **Model agreement is not evidence.** Two models concurring measures shared
  priors. Disagreement is a cheap signal that a human should look; agreement is
  silence, not confirmation.

---

## What it would take to be a product

Honest list, in order.

1. **Configuration instead of constants.** Paths come from `paths.py` or
   arguments almost everywhere already; `bakeoff.py` and `consensus.py` do not.
2. **A provider seam for the vision model.** `classify_live.py` speaks one API.
   The bake-off harness proves the comparison method is already there.
3. **The query layer.** SQLite + FTS5 exists now. Natural-language-to-SQL over a
   small fixed schema is a thin layer on top, and semantic search over the
   `subject` text already generated for 97,484 files is another.
4. **The enrichment loop as a UI**, scheduled on leverage, writing to the
   journal. A swipe prototype exists in `engine/swipe/`.
5. **Packaging.** It is a set of scripts sharing conventions, not a library with
   an installable surface.

What it would *not* need is a rewrite. The pipeline has run end to end on a real
library of 82,194 files, and the parts that broke broke in ways that are written
down in `docs/LEARNINGS.md` with the incident attached to each one.
