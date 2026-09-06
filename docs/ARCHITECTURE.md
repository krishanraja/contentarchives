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
ontology. `D:` is the source of truth for what has been consolidated.

**`H:` — staging now, mirror later.** Two distinct roles, in sequence:

1. *Now:* the place for anything oversized, or anything moving between machines.
   Two machines both mount it, so it is the transfer channel as well as the overflow
   valve. Working files a session needs another session to see go here.
2. *Later:* once `D:` has been audited in full, `H:` becomes the cloud mirror of `D:`.
   **Not before.** Mirroring an unaudited library propagates its mistakes, and a
   sync is not a backup — deletions and corruption replicate.

**`G:`** is a separate, smaller cloud account. Used for small-file messaging between
machines. Not a storage tier.

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
| `docs/HANDOVER.md` | narrative handover for a new session | a human or session, by hand |
| `docs/LEARNINGS.md` | rules, each with the incident that produced it | append when something is learned the hard way |

### Protocol for a session picking this up

1. `git pull`
2. Read `state/STATE.json` first — it is generated, so it cannot have drifted.
3. Read `docs/HANDOVER.md` for context the numbers do not carry.
4. Read `docs/LEARNINGS.md` **before changing any exclusion or deletion rule.**
5. Do the work.
6. Run `python tools/track.py`, commit `state/`, push.

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
