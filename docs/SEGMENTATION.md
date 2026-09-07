# What the library is allowed to contain

The next major checkpoint after the Takeout ingest. Specified by Krish
2026-09-07; this file is the record of it, so the requirement does not decay into
whatever the next session remembers of it.

---

## 1. The requirement

`PhotoLibrary\` holds **personal memories, and nothing else**. Anything that is
not a memory comes out of the chronology and lives somewhere with a structure of
its own - a `YYYY\YYYY-MM\` tree is right for a life and wrong for everything
else.

| Class | Where it goes |
|---|---|
| Personal memories | the chronology, split Personal / Communal |
| Screenshots | **deleted** - see the rule conflict below |
| Content production, podcasts | out of the chronology, own structure |
| Documents, admin | out of the chronology, own structure |
| Everything else | segmentation to be proposed, also out of the chronology |

And the split itself must be **audited**, not assumed: every file in `Personal\`
should be personal, everything in `Communal\` communal.

## 2. The end state

Exactly two locations hold all of it, and they are **perfect clones**:

```
D:\PhotoLibrary                             H:\My Drive\_photo-consolidation
        \___________ identical structure, identical data ___________/
```

---

## 3. Three decisions needed before this starts

**(a) Does everything move inside `D:\PhotoLibrary\`?**
Today `Archive\` (documents) and `ContentProduction\` are **siblings** of
`PhotoLibrary\`, not inside it. The requirement names `D:\PhotoLibrary` as one of
the two locations holding *all* content, which would mean they move under it -
but they may just have been named loosely. The clone target cannot be defined
until this is settled, because it decides what the root of the mirror even is.

**(b) "All screenshots should be deleted" conflicts with a standing rule.**
The rule is that a classifier may **move** a file but never delete one, and it
exists because 45 files were lost early in this project. 10,540 files already sit
in `_Review\` awaiting exactly this judgement.

The reconciliation, which achieves the instruction without giving a classifier a
delete: classify into `_Review\`, Krish confirms the bucket, **then** it is
emptied in one reviewed action and journalled. The classifier still never
deletes; the human does, once, with the list in front of them. If Krish wants the
classifier to delete directly, that is his call to make explicitly - it should not
be inferred from a one-line instruction.

**(c) What are the remaining categories?**
Deliberately left to be proposed rather than guessed, and it needs the data: the
proposal comes from what is actually in the library after the ingest, not from a
taxonomy invented in advance.

---

## 4. The thing that makes the clone hard

**`H:` does not currently hold a library. It holds raw inputs.**

`_photo-consolidation\` contains `from-boogles`, `from-lorimer`, `from-wd6400`,
`in` and `out` - unprocessed material from other machines, never deduplicated
against anything. `D:\PhotoLibrary` is the opposite: curated, deduplicated, dated,
split.

So these two are not two copies that have drifted apart and need reconciling.
They are **a library and a pile of inputs**, and no sync tool reconciles those -
running one in either direction produces something worse than both. Which means:

- **Cloning H to D would inject 180 GB of undeduplicated material** into a
  curated library.
- **Cloning D to H would destroy the only copy of inputs** not yet ingested.

### The order that resolves it

```
1. INGEST     every H: input into D:, streamed in batches:
              pull -> hash-dedup -> new files enter the library -> delete batch.
              D: gains only what belongs in the library.

2. SEGMENT    the work in section 1: audit the split, evict non-memories.

3. AUDIT      prove the library is internally consistent.

4. BREAKOUT   Krish looks at it, while corrections still cost seconds.

5. CLONE      only now. D: is canonical; H: is rebuilt from it.

6. PROVE      manifest both sides, compare by content hash, read H: back
              through the cloud API and never through the mount.
```

**Step 5 is a rebuild, not a merge.** Once every input has been ingested and
verified present in `D:`, the raw folders on `H:` have served their purpose and
are retired - and `H:` is written fresh as a copy of the organised library. That
is what makes the two sides identical by construction rather than by reconciling
two different things and hoping.

The retirement is the dangerous step, so it is gated: an input folder is removed
only after its content is **verified by hash** inside `D:`, never merely because
the ingest reported success.

---

## 5. Sequencing note

Segmentation comes **before** the clone, not after. Every file moved after
cloning costs a re-upload and a re-verification; every file moved before it costs
a rename on a local disk. The breakout session sits in the same gap for the same
reason.
