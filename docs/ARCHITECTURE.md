# Architecture and canon

**This repository is the canonical record of consolidation progress.** Multiple
sessions, on multiple machines, read and write it. Nothing about project state lives
only in a conversation.

---

## Storage model

Three tiers, each with one job:

```
        ┌────────────┐   oversized / cross-machine    ┌────────────┐
        │  machine   │ ─────────── staging ─────────► │     H:     │
        │   local    │                                │  2 TB cloud│
        └────────────┘                                └────────────┘
              │                                              ▲
              │  everything converges here                   │
              ▼                                              │
        ┌────────────────────────────┐   full sync, after    │
        │            D:              │   the audit passes    │
        │  the single local endpoint │ ──────────────────────┘
        │  PhotoLibrary + Content    │
        └────────────────────────────┘
```

**`D:` — the ultimate local endpoint.** Everything converges here. `PhotoLibrary/`
holds personal media organised by date; `ContentProduction/` holds work output
(podcasts, interviews, published video) and is deliberately outside the library
ontology; `Archive/` holds everything else worth keeping, filed by what it is rather
than when it arrived. `D:` is the source of truth for what has been consolidated.

The schema and the retention rules are in [ORGANISING.md](ORGANISING.md), written to
be applied to every other machine, drive and cloud account in turn.

**`H:` — staging now, mirror later.** Two distinct roles, in sequence:

1. *Now:* the place for anything oversized, or anything moving between machines.
   Two machines both mount it, so it is the transfer channel as well as the overflow
   valve. Working files a session needs another session to see go here.
2. *Later:* once `D:` has been audited in full, `H:` becomes the cloud mirror of `D:`.
   **Not before.** Mirroring an unaudited library propagates its mistakes, and a
   sync is not a backup — deletions and corruption replicate.

**`G:`** is a separate, smaller cloud account. Used for small-file messaging between
machines. Not a storage tier.

### Never read free space from a Drive mount

`Get-PSDrive H:` reports the free space of the **local cache volume**, not the cloud
quota. Both mounts echo `C:`'s figure, which is off by more than an order of
magnitude and in the wrong direction — it makes a 2 TB destination look like it has
a hundred gigabytes. Capacity for these mounts comes from the account, not the
filesystem.

The reverse trap sits on the upload side: Drive for Desktop **stages uploads through
that local cache on `C:`**. So the destination has room and the source has room, and
a single large copy still fills the system drive and fails midway. Batch it, with a
cache check between batches.

Expect that cache to hold the data for a while after the copy finishes. A 140 GB
publish returned only ~130 GB of the ~189 GB freed on `C:`; the balance was Drive's
cache, released on its own schedule. Do not plan the next job around space that a
completed upload has not given back yet.

### Never read sync state from a Drive mount either

The same illusion, one layer along, and it is the more dangerous of the two: **a
write into the mount lands in the local cache and uploads behind it.** Reading a file
back from `H:` reads the cache. If you verify a publish by re-reading the mount, you
have compared local bytes against local bytes and learned nothing about the cloud.

This was measured, not theorised. After a 140 GB publish that verified 17,102/17,102
by content hash *against the mount*, the files written last were **absent from the
cloud entirely**, and a rewritten 12 KB file still served its previous version through
the Drive API an hour later.

Drive for Desktop keeps its backlog in SQLite:

```
%LOCALAPPDATA%\Google\DriveFS\<account_id>\metadata_sqlite_db
```

The `operations` table is work not yet committed to the cloud. Copy the file first
(`-wal` and `-shm` too), then count rows; it drains to 0 when the client is genuinely
finished. On the 140 GB publish it started at 21,615 and took about three hours at
1.6–3.5 ops/s.

**So: sync completion comes from the client's queue, and existence comes from the
cloud's API. Neither answer is available from the mounted filesystem.** Sampling a
few files through the API confirms presence and size; it is not content proof, since
hashing the cloud copy means downloading it again.

This matters most at exactly the moment it is easiest to skip — deciding a source is
safe to erase. See [LEARNINGS.md](LEARNINGS.md) rule 25.

---

## The sequence, and why the order matters

```
  consolidate  ──►  audit  ──►  mirror D: to H:  ──►  quarantine into batches
```

- **Consolidate** every source into `D:`. In progress.
- **Audit** before mirroring: segmentation correct, `NoDate` reviewed, origins
  verified, nothing personal misfiled as work or vice versa.
- **Mirror** only after the audit. Back up `PhotoLibrary/` and `ContentProduction/`
  and nothing else — hardlinked content would otherwise upload twice.
- **Quarantine** personal from communal family material, in batches selected by
  *origin folder*. This is why the origin map exists.

---

## Canon: how sessions share state

**Never describe project state from memory.** It has been wrong repeatedly — a
narrated summary drifts from reality within minutes, and the drift is invisible.

State is *derived from artefacts*, then committed:

| File | What it is | Written by |
|---|---|---|
| `state/STATE.json` | machine-readable state, all figures counted from disk | `tools/track.py` |
| `state/PROGRESS.md` | the same, human-readable | `tools/track.py` |
| `state/origin-folders.csv` | every origin folder, file counts, sizes, year spans | `tools/origin_map.py` |

`tools/refresh.py` runs all three in the right order; `--check` verifies without
writing.
| `docs/HANDOVER.md` | narrative handover for a new session | a human or session, by hand |
| `docs/LEARNINGS.md` | rules, each with the incident that produced it | append when something is learned the hard way |

### Protocol for a session picking this up

Start at [`RESUME.md`](../RESUME.md) — it carries the current position and the open
work. This section is the underlying discipline.

1. `git pull`
2. Read `state/STATE.json` first — it is generated, so it cannot have drifted.
3. Read `docs/HANDOVER.md` for context the numbers do not carry.
4. Read `docs/LEARNINGS.md` **before changing any exclusion or deletion rule.**
5. Do the work.
6. Run `python tools/refresh.py` and `python tools/check_manifest.py`, update
   `RESUME.md` if the position changed, commit `state/`, push.

### Protocol for finishing a session

Commit state even if the work is incomplete — especially then. A half-finished
ingest with an accurate checkpoint is recoverable; one with a stale record is not.

If something was learned the hard way, add it to `LEARNINGS.md` with the incident
that produced it. The incident is the part that makes the rule stick.

---

## What is published, and what is not

The origin map exists so a batch can be chosen by *where it came from*. That is the
only practical way to separate personal material from communal family content across
59,000 files — nobody sorts them one at a time.

This repo is public, so it carries the folder-level view only:

| | where | why |
|---|---|---|
| `state/origin-folders.csv` | committed here | 637 folders — the level decisions are actually made at |
| `ORIGIN-MAP.csv` (per file) | library machine only | regenerable at any time with `tools/origin_map.py` |
| `SENSITIVE-FILES.csv` | library machine only | names the documents themselves |
| `redaction-key.json` | library machine only | reverses the pseudonyms below |

**Pseudonyms are stable.** A person's name maps to the same `PERSON-x` label in every
file, every run. Batches stay distinguishable without naming anyone.

**The tripwire is the real safeguard.** `tools/publish_state.py` scans the *redacted*
output for anything still resembling identity, medical or financial material, and
refuses to write anything at all if it finds a hit. Its first run earned its keep: it
caught that the per-file map leaks through **filenames**, not just folder names —
passport, OCI and spouse-visa scans name themselves. That is why the per-file map is
not published.

New sources will bring new names. The tripwire turns that from a silent leak into a
failed run. **If it fires, add the term to the key — never weaken the pattern.**

### A finding worth acting on

The same scan flagged **34 files in the library whose own filenames describe identity
or financial documents** — passports, OCI cards, visas, birth certificates. They were
swept in from `Downloads` and `Documents` folders alongside genuine photos. A photo
library is the wrong home for them; they belong in the quarantine pass.

---

## Machines

| Role | Notes |
|---|---|
| Consolidation machine | holds `D:`, mounts `G:` and `H:`, does the ingest work |
| Second machine | mounts `G:` and `H:` but has no `D:`. Surveyed and transferred its candidates via the shared drive. |

Sessions on different machines cannot see each other's local disks. The shared cloud
mounts are the only common ground — which is why staging goes through `H:` and
small-file messaging through `G:`.
