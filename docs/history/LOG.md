# History log

Newest first. Entries are written by the docs steward (see the steward link in
NOW.md) and by humans doing the same job by hand. Nothing in this file
describes current behaviour; NOW.md and the state doc do.

This repo already keeps its chronology in two places the steward does not
duplicate: `docs/rescues/` holds one dated record per source, and
`docs/LEARNINGS.md` holds the numbered rules in the order they were paid for.
This log records what the steward did to the documentation and when.

## 2026-09-07

- reconciled at `62d6aa0`: `main` gained Krish's commit "Learning 28: two names for one file is not two copies", adding rule 28 to `docs/LEARNINGS.md` and rewriting RESUME.md's "Where things stand" section from midday to overnight, folding in the Takeout merge and the guarded-delete fix that had already landed. NOW.md re-headed, given a "What changed recently" bullet in the commit's own words, a story bullet added under "Who it is for", and the rule count in "Read next" moved to 28. The "midday" references in "Where it is right now" and "What is next" were updated to overnight, since RESUME.md no longer predates the Takeout merge. The now-resolved "Do not trust" line about that stale section was replaced with one naming the unreconciled gap between state/STATE.json's disk-free figures (generated at `ee3b550`) and RESUME.md's later, unregenerated overnight figures.
- reconciled at `07a81b2`: `main` gained Krish's commit "Guard every deletion, and fix the cache that manufactured 222 GB of duplicates" (learning 27, `guarded_delete.py`, `reclaim_duplicates.py`). NOW.md re-headed, given the bullet in the commit's own words, its duplicate counts marked as undercounts, the reclaim added to "What is next", and the rule count in "Read next" moved to 27. The steward-secret reminder was removed from "What is waiting on Krish" at Krish's instruction, the secret being in place.
- reconciled at `ee3b550`: `main` moved by one non-steward commit ("Merge the full 2026-09-07 Takeout export, verified, and reclaim 21 GB") while the bootstrap was under review. `NOW.md` was re-pointed at `ee3b550` before the first push, its figures re-quoted from the regenerated `state/STATE.json` (2026-09-07T19:14:52), a bullet added for the merge, and `docs/SEGMENTATION.md` (new in that commit) added to "Read next" and the README index. The HANDOVER timeline paragraph gained one sentence for the same merge.
- decision: docs steward adopted for this repo (Krish, 2026-09-07). Bootstrapped by hand at `08def7e`; `.github/workflows/docs-steward.yml` calls the shared workflow in `krishanraja/control-center` on every push to `main` and nightly at 20:35 UTC.
- indexed: `docs/rescues/` is the per-source chronology, one dated file per source (`2026-09-06-wd6400.md` is the first and the model). The steward does not move or duplicate these files.
- indexed: `docs/LEARNINGS.md` is the append-only rule chronology, 26 numbered rules at `08def7e`, each with the incident that produced it. The steward never edits an existing rule.
- reconciled at `08def7e`: `NOW.md` written for the first time per `docs/steward/SCHEMA.md`. Figures quoted only from `state/STATE.json` and `state/PROGRESS.md`, never narrated (re-quoted at `ee3b550`, see above).
- reconciled at `08def7e`: `docs/HANDOVER.md` gained one dated timeline paragraph near the top covering the repo's commits of 2026-09-06 and 2026-09-07. Its "Last verified" stamp was left at 2026-09-06 because the rest of the body was not re-verified against disk; its tables predate the state file at HEAD, and NOW.md's "Do not trust" says so.
- reconciled at `08def7e`: `README.md` doc index gained rows for `NOW.md`, `docs/history/LOG.md`, `docs/MIRROR.md` and `docs/SEGMENTATION.md` (the last two had no index row).
- waiting on Krish: `docs/HANDOVER.md` has drifted from the state file at HEAD. Its tables (59,450 files, "Library 328", verified 2026-09-06) predate `state/STATE.json` (90,408 files, generated 2026-09-07T19:14:52), and its outstanding item 3 describes the 2026-09-05 Takeout export as still downloading where `RESUME.md` section 2 says that export is dead and `ee3b550` says the replacement is fully ingested. The steward cannot recount from disk, so the figures were left as they are and NOW.md's "Do not trust" names the drift. A session on the library machine should run `tools/refresh.py` and revise the handover.
- reconciled at `08def7e`: no duplicate, unlabelled or stale-stamped document found. The steward digest for this range reported "Duplicate and unlabelled candidates: None." No file was moved.
