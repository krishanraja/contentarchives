# RESUME PHOTOLIBRARY

**You have been asked to resume the media consolidation.**

> **Machine state first.** Read **RIGHT NOW** below before running any command in
> this file, including the ones directly below. It is the handover point, and it
> says what is running unattended at this moment.

```bash
cd C:\Users\krish\dev\contentarchives
git pull
python tools/audit_previous_session.py   # FIRST - verify, do not assume
python tools/refresh.py --check          # verify state, write nothing
```

**Start with the audit, and report its failures to the user before doing anything
else.** The previous session graded its own work, at the time, while inclined to see
it as finished — the worst vantage point there is. The audit checks the claims
against the filesystem instead.

A FAIL is not automatically a mistake: work deliberately deferred fails the same
checks as work forgotten. What a FAIL means is *do not treat this as done, and do
not build on it*. Tell the user which items failed, and why, before extending any of
them.

This step exists because a schema was written to this repo and then described as
complete when only the documentation had been produced. `docs/ORGANISING.md` defined
an Archive layout; `D:\Archive` did not exist. Documenting a structure and applying
it are different acts, and only one of them is visible on disk.

Then read [`state/PROGRESS.md`](state/PROGRESS.md) — generated, so it cannot have
drifted — and [`docs/LEARNINGS.md`](docs/LEARNINGS.md) **before changing any
exclusion, deletion or classification rule.**

----

## THE REPO IS A CONVEYOR OF STAGES (since 2026-09-15)

Work is organised by the part of the process it serves, not by when it was
written: `stages/01_sources` through `stages/12_canon`, plus `guards/`. Each
`STAGE.md` names the stage's inputs, outputs, invariants, code, tests, and the
learnings it OWNS - with the exact function or test that enforces each one.

**Adding or changing machinery:** find its stage, read that `STAGE.md`'s Lessons
table (not all fifty learnings from memory), use `guards/` rather than
re-implementing a check, and add your file to the stage's Code table.
`tests/test_stage_contracts.py` fails the build if a code file has no stage, a
learning has no owner, or an enforcement a table cites has stopped existing.
**A new learning fails the build until a stage claims it.**

Run the whole suite before trusting a change - twelve Python files and three
under PowerShell. The PowerShell three are easy to forget and cover the
supervisor itself, re-arming, and the guard that refuses a chain which cannot
parse:

```powershell
Get-ChildItem tests\test_*.py  | ForEach-Object { python -u $_.FullName }
Get-ChildItem tests\test_*.ps1 | ForEach-Object { pwsh -NoProfile -File $_.FullName }
```

`tests\test_steps.ps1` supervises real processes and sleeps through their
checkpoints, so the full run takes a couple of minutes rather than seconds.

Current debt, printed by the contracts test - **read it from the test, never from
here**: 13 stages, **114 of 114** code files owned, 55 learnings, 50 enforced by
a named function or test, **5 enforced only in prose: 8, 13, 17, 24, 29**. This
paragraph carried three stale numbers for a week because it was written from
memory instead of from the run.

**Migration, not finished.** The `STAGE.md` files list code where it lives today.

- **Phase 2 - DONE 2026-09-16. `scripts/` no longer exists.** Every stage holds
  the machinery it claims: 01 sources 9, 02 ingest 14, 03 dating 1,
  04 inventory 4, 05 enrich 19, 06 faces 8, 07 people 6, 08 index 2,
  09 segment 9, 10 reclaim 13, 11 mirror 3, 12 canon 1. It went from 54 `.py`
  files to none, and `scripts/README.md` went with it - it indexed all 56 by
  their old paths, and the twelve `STAGE.md` Code tables already own every one.

  **Every chain derives the repo root** - `Split-Path -Parent (Split-Path
  -Parent $PSScriptRoot)` - rather than hardcoding
  `C:\Users\krish\dev\contentarchives`, which four of them did. The repo works
  from any checkout, the same argument as `stagepath`'s walk-up.

  **What stays put, by a convention every move settled:** `tools/` holds a
  stage's operator-facing utilities (8 files: 04 inventory keeps four, 12 canon
  three, 09 segment's `audit_split.py`), and `contentarchives/` holds the
  reusable cores (`safety.py`, `dedupe.py`, `dating.py`). A stage owns the
  logic; it does not have to own the file.

  **The publisher is retired**: `D:\_PhotoAudit\scripts\publish_scripts.py`
  refuses to run, because the repo holds the ONE runnable copy and `--apply`
  would overwrite it with pseudonym copies that cannot execute. Its ancestor
  `D:\_PhotoAudit\scripts\paths.py` is marked superseded but NOT deleted -
  machine-resident scripts may still import it.

  **Read `tests/test_imports.py` before the next move.** Six of its seven
  sections were written because a move broke something silently: libraries that
  import, guarded scripts that import without running, a shrinking list of
  unguarded ones, every subprocess launch pointing at a file that exists, every
  `stagepath.*` caller importing it, and nothing putting `D:\_PhotoAudit` on
  `sys.path`. That last one cost eleven scripts' imports in one afternoon.
- **Phase 3 - DONE 2026-09-16**, once `VIDEO FACES COMPLETE` meant nothing was
  running. 39 files moved with `git mv`: stages 05 enrich, 06 faces, 07 people
  and 08 index into their folders, and `paths.py`, `steps.ps1`, `arm.ps1` and
  `rearm_when.ps1` into `guards/`. Each chain script now lives with the stage it
  drives. `engine/` and `scripts/chains/` are **gone** - both were left empty by
  the move and removed on 2026-09-16; `engine/README.md`, which described the
  enrichment design in a directory that held no code, moved to
  `stages/05_enrich/README.md` with its usage paths corrected. Imports go through
  `stagepath.py` - two lines, no relative depth, and `stagepath.script("x.py")`
  for anything launched as a subprocess.

----

## RIGHT NOW: round 19 is with Krish; two guards were fixed getting it out (2026-09-17, 22:20)

**Round 19 is sent** - `D:\_PhotoAudit\PEOPLE.html`, 60 rows, 371 crops, both
gates passed. It is the first sheet built to Krish's two new decisions:

- **the first 25 rows are the priority queue**: the clusters behind the 29
  photographs that lost their only name when the stale-label fix landed
  (`D:\_PhotoAudit\PRIORITY-CLUSTERS.csv`). He chose "drop it and queue those".
  They hold 1-4 faces each, so a floor of 8 would have binned every one - the
  sheet passes them explicitly with `--clusters` and applies by hand every
  filter that flag bypasses (answered, majority-Communal).
- **the other 35 come from the ranked pool at the 8+ floor**. He was asked where
  the floor should sit, shown the measured distribution, and chose **8+
  photographs**: 292 clusters, ~5 rounds, and then the rounds are DONE.

`--min-photos` is that floor, and when nothing clears it `people_sheet.py` says
**THE NAMING ROUNDS ARE DONE** and writes no sheet, because an empty page and a
finished job look identical to whoever opens it (learning 44).

### THE REPEAT GUARD WAS BLESSING AN EMPTY BASELINE

`check_repeats.py` matched `PEOPLE-round\d+\.html` in `D:\_PhotoAudit`. **There
are no such files** - every round has overwritten one `PEOPLE.html`. So for
round 19 it read **0 earlier sheets**, compared 60 rows against an empty set, and
printed "CLEAN - every row is new". I nearly sent the sheet on that.

Two fixes, because the pattern was only half the problem:

- the baseline now comes from **the journal**, which holds every row ever
  offered - named, `declined`, or `needs_identifying` - and cannot be lost by a
  file being overwritten. Real baseline: **993 merge groups**. Round 19 against
  it: **0 repeats, no row twice**.
- an empty baseline now **refuses** with exit 2 and says CANNOT TELL, instead of
  reporting clean. Second time this file has reported clean while measuring
  nothing; the first was the `[1-6]` pattern that froze at 186 rows.

Its test passed throughout, because it fabricates `PEOPLE-round1.html` fixtures
and so tested the matcher against a world that no longer exists.
`tests/test_people_rounds.py` now watches the empty-baseline refusal and the
journal baseline, including that **a declined row is a repeat** - a refusal is an
answer.

### FOUR THINGS I GOT WRONG TODAY, AND WHAT EACH ONE COST

Kept because each was caught by measuring, and the next session should expect the
same rate rather than trust a confident line in this file.

| claim I made | truth | how it was caught |
|---|---|---|
| "250 photographs lost a name I cannot account for" | **29**, as captured. I compared `count(distinct hash)` to a FILES coverage line - two different units | re-derived both measures side by side |
| "`Kiran` was in the tag layer after all" | it never was. My own log line printed 4 names beside 1 row count, and I believed it over the evidence | `tags` holds no `Kiran` row at all |
| "the largest unnamed cluster covers 9 photographs" | **10**, and the pool is 57,793 clusters - I measured a pool already truncated by `--top 3` | ran the full distribution |
| "the sheet is gated, both checks pass" | gate 2 had read nothing. Also invoked both gates on remembered flags (`--sheet`) that neither accepts | read their argument lists |

The log line is fixed to print **per name**, so "superseded" can no longer be
read as "dropped something".

----

## The Rishis, and the defect that came out of them (2026-09-17, 21:50)

### RESOLVED: the three Rishis

Krish: *"I think we need to redo the Rishi's the same way we redid the Kiran's."*
He was shown all ten clusters on one page (`D:\_PhotoAudit\RISHI.html`, 9 rows,
105 crops, `verify_people_sheet.py` exit 0) and answered. Recorded, rebuilt, and
re-derived from the index:

| person | clusters | photographs on the index |
|---|---|---|
| **Rishi Unadkat** | `c290` + `c36` (ONE merge group), `c17449` | 573 |
| **Rishi Blainey** | `c1303`, `c2811`, `c13897`, `c29781`, `c11525` | 207 |
| **Rishi Chande** | `c993`, `c480` | 31 |

**MY INFERENCE WOULD HAVE BEEN WRONG AGAIN.** I expected the 654-photograph,
eighteen-year cluster to stay plain "Rishi" and the 9-photograph `c17449` to be
the outlier. The big one IS Rishi Unadkat. That is twice in two rounds that the
counts and dates pointed the wrong way; `name_clusters.py` refuses to decide for
exactly this reason.

`c36` is the tenth cluster and he did not type it: it shares merge group `c290`,
so the row he judged pooled both clusters' faces (287 + 280 tags). **Asked, not
assumed** - and recorded with its provenance in the note, so the journal shows
where that one came from.

### FIXED: a stale `tags` person layer that no answer could supersede

The index still shows a person called plain **`Rishi` on 97 photographs** and
**`Rishi (baby)` on 38**, though NO cluster asserts either name any more.

`resolve_people()` in `stages/08_index/build_db.py` takes the latest journal
answer per cluster (correct - that is why no cluster says bare `Rishi`), then at
line 352 appends **every `tags` row with `tag='person'`**. That layer was written
per photograph by an earlier enrichment pass, with no cluster behind it, so a
name Krish has since corrected survives there for ever: `INSERT OR IGNORE` only
dedupes identical `(hash, person)` pairs and nothing removes a stale name. The 97
photographs' faces trace to `c3735`, `c50767`, `c166` - not Rishi clusters at all.

Measured library-wide, the blast radius is tiny and exact:

| | | measure |
|---|---|---|
| names the journal has replaced | **4** | `Anita (Mak)`, `Kiran`, `Rishi`, `Rishi (baby)` |
| of those, names present in `tags` | **2** | only `Rishi` (97 rows) and `Rishi (baby)` (38) |
| stale tag rows not re-imported | **135** | 97 + 38 |
| photographs that lost their only name | **29** | hashes, captured before AND reconstructed after |
| photographs with no human-sourced name | 2,107 | hashes - they keep their tag names |

**Krish chose "drop it and queue those"**, told the cost. `tags` is untouched:
only the derived table changes, so a rebuild reverses it. The 25 unanswered merge
groups behind those 29 photographs are the first 25 rows of round 19, because
after the rebuild those photographs are indistinguishable from any other unnamed
one - so they were captured first, in `D:\_PhotoAudit\PRIORITY-CLUSTERS.csv`.

`test_build_db.py` section 8 is **proven to engage**: HEAD's `resolve_people` and
the new one run side by side on the same fixture give `['Dad','Mother','Mum']`
and `['Dad','Mother']`, while `Nanna` - an uncontradicted tag name that is a
photograph's only name - survives in both. Section 5 passed either way, which is
why it was not enough.

### I OVERSTATED THE KIRAN VERIFICATION, and it needs saying

A round earlier I reported "plain `Kiran` gone" as proof the rename had taken.
`Kiran` does read 0 - but only because that name never existed in the tag layer.
The check tested nothing about supersession and would have passed either way.
True as a fact, worthless as evidence, and presented as evidence. It is the same
trap already recorded below about the merge's own reassurance: **a check that did
not engage is not evidence that it did** (learning 54).

**Nothing is running unattended. The next move is Krish's.**

**Rounds 1-18 are recorded and BUILT IN.** Round 18's answers went into
`D:\_enrichment\answers.csv` and the rebuild finished cleanly at 21:23 - pid 2564
exited 0, `wrote D:\_PhotoAudit\library.db in 130s`, empty stderr, no `.tmp` left
behind. The live index was already swapped at 21:23:09 while the process still
ran; that is `report()` running after `promote()`, not a half-finished write, and
it was confirmed rather than assumed. Totals now:

**Every figure here names the measure it came from.** On 2026-09-16 I compared
`count(distinct hash)` in `photo_people` against the `person` line of the
coverage report, which counts FILES, and invented a 250-photograph loss out of
two different units. A number in this file without its measure is how that
happens.

| | | measure |
|---|---|---|
| human answers in the journal | **1,096** | rows in `answers.csv` |
| people named | **262** | `count(distinct person)` in `photo_people` |
| files with a person | **24,870** | `v_files.person` not null - the coverage line |
| photographs with a person | **24,620** | `count(distinct hash)` in `photo_people` |
| person rows | **44,525** | `count(*)` in `photo_people` |

The two photograph counts differ because one hash can be several files. Neither
is wrong; quoting one as the other is.

**Every sheet is crop-verified and repeat-checked before he sees it** - he asked
for that after batches he had refused came back a second time. Round 18 was 60
rows, 536 crops, `verify_people_sheet.py` exit 0, `check_repeats.py` 0 repeats
against all 846 rows of rounds 1-17.

Round 18's two new names, **Gabby** and **Sinitta**, are profile terms now
(`profile_coverage.py --apply`, 270 terms, **0 of 261 named people
unprotected**). Run that tool after every round: Lily sat unprotected for eight
rounds because the seeding dropped names under five characters.

**The open question I have not asked, and should.** Reach per round is falling -
1,058 photographs unlocked, then 540 - because `--top 60` ranks by cluster size
and the big clusters are done. Worth asking him whether to keep ranking by size,
add a cluster-size floor, or rank by what unlocks the most Communal photographs
for Bharti. Do not change the ranking without asking.

### RESOLVED: the two Kirans, and why guessing would have been wrong (2026-09-17)

Krish: *"I have labelled two different people Kiran, one of them should be Kiran
Nathwani."* The journal held three `Kiran` clusters, and his round 17 answer
added a fourth. He was shown all four side by side and answered:

| cluster | photographs | span | is |
|---|---|---|---|
| `c306` | 157 | 2012-2026 | **Kiran Nathwani** |
| `c1160` | 11 | 2017-2024 | **Kiran Patel** |
| `c1165` | 10 | 2018-2023 | **Kiran Nathwani** |
| `c4122` | 10 | 2019 | **Kiran Nathwani** |

Verified on the index after rebuilding: **Kiran Nathwani 177 photographs, Kiran
Patel 11**, and plain `Kiran` gone. 177 rather than 178 because a photograph
holding two of those clusters counts once.

**MY INFERENCE WOULD HAVE BEEN WRONG.** I expected the large fourteen-year
cluster to stay plain "Kiran" and one of the two small round-15 clusters to
become Nathwani. It is the other way round: the 157-photograph cluster is
Nathwani, and the small `c1160` is the different person. Resolving this by
reasoning about counts and dates would have renamed a real person across 157
photographs. Asking cost one page - `--clusters` in `people_sheet.py` takes
explicit ids and bypasses both the ranking and the already-answered filter, so
any future "which of these is which" question is one command.

Recorded as four NEW journal rows: it is append-only and a later human answer
outranks an earlier one, so nothing was edited. Both full names are now profile
terms in their own right, because they had been covered only by the short term
`kiran` - cover that vanishes silently the day that term is removed.

**One caveat about the merge's own reassurance.** It printed "no group mixes two
differently-named people", but all four clusters stayed UNMERGED - each is still
its own group - so that check held because nothing merged, not because it
arbitrated anything. Three separate clusters now legitimately share the name
Kiran Nathwani, which `record_people.py` states is expected. A check that did
not engage is not evidence that it did.

### NO COMMUNAL FACES IN KRISH'S SHEETS (decided 2026-09-17)

Krish, at the end of round 14's answers: *"Do not make me identify any more
faces from Communal any more."* Communal is Bharti's to enrich. `people_sheet.py`
now skips clusters whose photographs are **majority Communal** - 3,283 groups,
6,460 photographs, excluded from round 15 - and `--include-communal` overrides it
for anyone who needs the old behaviour.

**Two decisions of his to leave alone.** He was shown that true Communal is only
7% of what remains (4,054 of 58,033 clusters) while the bulk is 14,642 unsided
Pending-Segmentation/NoDate clusters - where the scanned old photo libraries sit
- and chose **true Communal only**, so the unsided material stays in his sheets.
He also chose to queue **nothing** to Bharti for now: 18,696 clusters would have
qualified, and nothing is written to the journal on his behalf. Do not widen the
filter or start queueing without asking him again.

**The side comes from `files.path`, never `files.side`.** That column holds the
top-level tree - `Media`, `Archive`, `_Review`, `ContentProduction` - so the
first version of this filter found no Personal photograph anywhere, reported 0
majority-Personal clusters out of 58,033, and would have excluded his entire
remaining queue. `side_of()` and `is_majority_communal()` are module-level
functions in `people_sheet.py` so `tests/test_people_rounds.py` section 7 calls
the same code the sheet calls, and is watched EXCLUDING a Communal cluster
rather than only passing.

**Both supervision fixes are in, and `-Progress` was chosen from a RECORDED
TRACE after two guesses failed and a third was about to.**

`-Verify` reads `OK library.db` after the rename rather than taking its "cannot
tell yet" escape - the branch that used to make the one check gating the whole
step pass on nothing.

`-Progress` returns a **running maximum** of `live + tmp + tmp-wal`, monotone by
construction. `Invoke-Step` treats any non-increase as a stall and four strikes
kills the work, so the signal must never decrease. Replaying all 40 samples of
`D:\_PhotoAudit\rebuild-progress-trace.csv` through each candidate:

| candidate | falls |
|---|---|
| v1 committed rows in `library.db.tmp` | never rose at all - one long transaction, a `mode=ro` reader sees nothing |
| v2 `tmp + tmp-wal`, else live | **2** - the temp files do not exist for the first ~30s, so it switches basis mid-run |
| v3 `live + tmp + tmp-wal` | **1** - 2,221,964,872 then 766,902,272 at the rename |
| v4 high-water mark (in use) | **0** |

v3 is the one I had already called "the honest signal" in this file. It takes a
strike at the end of EVERY run. The trace is the only reason it was not shipped.

`stages/08_index/sample_rebuild.py` produced it and stays in the repo for the
next time a signal is in doubt - `check_repeats.py` spent three rounds in a
session temp directory carrying a stale pattern, and an instrument a fix depends
on is the last thing that should be unversioned.

`-ExpectedUnits` is gone, which was right: it was 82,193, the FILE count, from
when progress was measured in rows, so the runner printed "RECALIBRATE: already
184,320 against an expected 82,193" - bytes against files. Harmless, since
divergence is reported and never enforced, but a number that means nothing is
worse than no number.

Rounds 12 and 13 both ran through `stages/07_people/chain_rounds.ps1`, one
command each, and the chain's own log caught three faults in its supervision
that are now fixed (learning 54, instances 6 and 7): `-Progress` counted
committed rows, then counted a file that vanishes on success - it reads the tmp
file if present and the live file otherwise, proven non-zero in both states; and
`-Verify`'s "cannot tell yet" branch was the one firing at the end, so the check
that gates the step passed on nothing - it now reports `OK library.db` after the
rename, which the round 13 log shows.

**The repeat guard lives in the repo now**, `stages/07_people/check_repeats.py`.
It lived in a session scratch directory and matched `PEOPLE-round[1-6].html` -
written when round 7 was next, never widened - so rounds 7-9 were invisible to it
and its baseline sat frozen at 186 for three runs while each sheet was called
clean. Widened to `round\d+`, the real baseline is 486, and rounds 7-12 all
re-check genuinely clean: nothing Krish refused ever came back. The verdicts were
right; the test behind them was narrower than the claim (learning 55).

**When his answers arrive there is ONE command.** Save the paste as
`names-r<N>.txt` beside the sheets, then record the answered round and build the
next - **but not until the Rishi question above is settled**, which is why the
`-Next` here is held rather than run:

```powershell
# HELD until Rishi is settled. Rounds 1-18 are recorded; 19 is the next sheet.
pwsh -NoProfile -File stages\07_people\chain_rounds.ps1 -Answered 19 -Next 20
```

The Rishi answer itself needs no `-Answered` round: record it as new journal rows
the way the four Kiran corrections were, rebuild, then resume the rounds.

It records (dry run first), merges at 0.68, rebuilds under `Invoke-Step`
supervision, builds the next sheet, and runs both gates - refusing to go on at
any step rather than carrying on. It writes `D:\_PhotoAudit\rounds.log` and, on
failure, `D:\_PhotoAudit\ROUNDS-HALTED.txt` saying why; delete that file once the
cause is fixed. Preflight refuses a missing answers file, a missing sheet, or a
next-sheet path that already exists.

**Do not reassemble the steps by hand.** They were hand-run wrappers in a session
temp directory - pipe9, pipe10, pipe11 - and three copies are how
`check_repeats.py` came to carry a stale `[1-6]` pattern for three rounds while
calling every sheet clean. There is one runner now, in the repo, and the old
wrappers are deleted.

`--sheet` inside it is not optional: it is what records a row he was shown and
left blank as *declined*, so it is never offered again. Without it, refused
clusters return.

**Two flaws in that chain's own supervision were found by reading its log after
round 11, and both are fixed** (learning 54, instances 5 and 6): `-Progress`
counted committed rows in `library.db.tmp` and therefore read zero throughout,
which would have killed a correct rebuild on a false stall - it measures bytes on
disk now; and `-Verify`'s "cannot tell yet" branch was the one that fired at the
end, because the tmp file had been renamed away, so the verify that gates the
step passed on nothing. It now reads whichever database exists, and treats a live
index with no person rows as WRONG.

**VIDEO FACES ARE COMPLETE** - 41,931 video faces are joined to the frozen
clusters. The chain described below is finished; its commands are kept because the
verification argument they make is the one to reuse for the next long job.

**THE RULE THIS PRODUCED, which still applies: audit every numbered learning
against every new component, written down, BEFORE arming anything unattended**
(learning 50). Done for the video chain on 2026-09-15: eleven gaps were found and
fixed, `tests/test_video_faces.py` now watches every guard pass and fail, and the
re-arm at 15:37 reaped three orphaned frame workers the old reaper would have
missed. That walk is not optional for the next long job.

**History, not instruction** - what the audit printed on 2026-09-15 at 15:15,
while the chain was still running. Do NOT read these as the current state:

- `[PASS] running jobs belong to an armed chain ... do NOT kill` - at the time,
  the python and ffmpeg processes were the video-faces chain doing its work.
  **That chain has since finished.** Any python or ffmpeg process found running
  now is unexplained until proven otherwise: check `arm.ps1 -Status` first.
- `[FAIL] identity documents moved out of the chronology - 5 still` - still open,
  still deliberate, waiting on Krish (see "Waiting on the user"). Report, do not act.
- Every other check passed. Re-run the audit rather than trusting this list.

```powershell
pwsh -NoProfile -File guards\arm.ps1 -Status -TaskName contentarchives-video-faces
Get-Content D:\_PhotoAudit\video-faces.log -Tail 8
```

Healthy looks like `state : Running`, a `CHECKPOINT` line every 15 minutes and a
`verify OK` line about hourly. Four steps, each resumable:

| step | what | expected |
|---|---|---|
| frames | `stages/06_faces/video_face_frames.py`, 3 shards, one frame per 30 s into `D:\_frames` | ~32,670 frames, ~7 h (80/min measured at 14:56) |
| faces | `stages/06_faces/faces_embed.py --frames`, ONE process, into `D:\_enrichment\faces.video.csv` | ~18 h at 0.5 img/s |
| assign | `stages/06_faces/assign_video_faces.py --apply`, joins the FROZEN clusters | minutes |
| rebuild | `stages/08_index/build_db.py` | ~19 min measured 2026-09-16 (82,193 files, 1,452,244 tags), not the ~8 min this said - it writes `library.db.tmp` and renames, and stays read-bound with flat writes for minutes at a time without being stuck. If the final swap fails on a lock, NOTHING IS LOST: the finished database is at `library.db.tmp` and `promote()` says how to put it in place (learning 55) |

The last line will be `VIDEO FACES COMPLETE`.

- **If it halted**, `D:\_PhotoAudit\VIDEO-FACES-HALTED.txt` says why. Fix the
  cause, delete that file, re-arm.
- **After a reboot the task is gone** (by design). Re-arm; frames and faces resume
  where they were, and assign skips itself if its tags are already in the store:

```powershell
pwsh -NoProfile -File guards\arm.ps1 -Chain chain_video_faces.ps1 -TaskName contentarchives-video-faces
```

### Where the naming is

- **Eighteen rounds offered, seventeen answered** (2026-09-15 to 17). 1,026
  answers in the journal `D:\_enrichment\answers.csv` - 258 distinct people
  named. After the last rebuild: 82,193 files indexed, **260** people on
  photographs, **24,546** photographs and videos carrying a name, **44,405**
  person-on-photograph rows. Krish 9,358, Bharti 5,098, Bhasker 2,672,
  Anya 1,916, Lily 1,747, Lauren 1,704.
- **The photographs each round unlocks is FALLING, and that is expected**: 1,058
  at round 9, then 833, 764, 720, 666. `people_sheet.py --top 60` takes the
  largest unnamed clusters first, so what remains is progressively smaller
  groups. Krish was asked on 2026-09-17 whether to switch to a different cut -
  a size floor, or the clusters that would unlock the most Communal photographs
  for Bharti - and has not answered yet. Do not change the cut without him.
- **The profile holds 268 personal terms**, and `profile_coverage.py` reports
  **0 of 258 named people unprotected**. Run
  `python stages/07_people/profile_coverage.py` after every round: it reads the
  journal, reports every named person the profile misses, measures each against
  the library, and `--apply` adds the ones that are not catch-alls - then asserts
  each through `is_personal()`, because the write succeeding is not the term
  working. It replaced five near-identical throwaway scripts that had
  accumulated in a session scratchpad across rounds 13-15, which is how
  `check_repeats.py` came to carry a stale pattern for three rounds.
  `D:\_PhotoAudit\profile.yaml`, never committed, backed up beside itself as
  `profile.yaml.bak-*`.
- **27 of the 222 people Krish had named were NOT protected by it until
  2026-09-16**, Lily among them - 1,724 photographs, named in round 4. The
  seeding rule kept a single name only if it was five or more characters, and
  every per-round top-up afterwards looked only at that round's new names, so
  nobody dropped at the start was ever revisited. All 27 measured and added;
  `tests/test_profile.py` section 6 now asserts every name in the journal is
  protected, through `is_personal()` on a real path.
- **The group-photograph question used to take over two minutes and now takes
  9.4 seconds**: `photo_people` had an index on `person` and none on `hash`,
  which is what every "how many photographs have two or more people" query
  groups by - and what `chain_rounds.ps1`'s `-Verify` joins on at every
  checkpoint, so the supervision was paying for it too.
- **A kept term must appear IN a path to protect it.** `mick evans` in the
  profile does nothing for a photograph named `mick at the pub`, and `david
  storey` does nothing for `tore`. Three real people were reported "already
  covered" and were not; all three are in the file now. When adding a name, call
  `is_personal()` on a real path rather than comparing the name against the term
  list by eye (learning 54, instances 4 and 5).
- **A photograph can carry many people** - `photo_people` holds one row per
  person per file (learning 49). The earlier `resolved` table had a `(hash, field)`
  primary key and silently kept only one name per photograph.
- **The loop is one command:** `stages/07_people/chain_rounds.ps1 -Answered N
  -Next M`. It runs record (dry run, then `--apply --sheet`), merge at 0.68, the
  rebuild under `Invoke-Step`, the next sheet, and both gates, halting rather
  than continuing at any failure. The individual scripts are still there and
  still runnable for debugging - `people_sheet.py`, `record_people.py`,
  `merge_clusters.py`, `build_db.py`, `verify_people_sheet.py`,
  `check_repeats.py` - but the chain is what should be run.
- **Answer conventions Krish uses:** `c123 = Name`. `c123 = for <who>` is a
  question queued for the game, recorded as `needs_identifying = <who>`.
  `c123 = unsure, blurry` is recorded as `unidentifiable` and never asked again.
  `c123 = ?` is `needs_identifying = yes`. A trailing ` - remark` is a note.
- **A cluster he was shown and did not name is DECLINED, not unanswered.**
  `record_people.py --sheet` writes those rows to the journal so no later sheet
  offers them again; 105 refusals were recorded retrospectively on 2026-09-16
  after he said "stop resending me batches I have refused to identify - they are
  unidentifiable". Rounds 7, 8 and 9 each verified 0 repeats.
- **A name longer than 60 characters is refused, and prose after a name becomes a
  note.** `c4576 = Krish. Agree with your recommendation...` records Krish, and
  keeps the sentence as the note.
- **Backed up off the library disk** to
  `G:\My Drive\Personal\Family\Photo library - answers backup\`: answers.csv,
  FACE-CLUSTERS.csv, CLUSTER-MERGES.csv and faces.0.csv. Hashing the copies
  through the mount only proved the LOCAL CACHE had them (learning 25); the
  upload was confirmed separately from Drive for Desktop's own queue - the
  `operations` table in `%LOCALAPPDATA%\Google\DriveFS\<account>\metadata_sqlite_db`
  read 0 for both accounts at 15:25. `record_people.py --apply` refreshes
  answers.csv there every time; re-check that queue before trusting a new copy.

### When `VIDEO FACES COMPLETE` appeared - all four steps are DONE (2026-09-16)

Kept because step 3's argument about joining on `(image, face_index)` rather than
by position is the one to reuse. `merge_clusters.py` now reads video faces:
41,931 of them joined, 7,896 clusters with 3+ faces, 305 named by a human, 378
unnamed clusters inheriting a name from a named sibling, and no group mixing two
differently-named people at threshold 0.68.

1. `python stages\06_faces\assign_video_faces.py --verify` and `--verify-db` - prove it.
2. Copy `D:\_enrichment\faces.video.csv` and `D:\_PhotoAudit\FACE-CLUSTERS-VIDEO.csv`
   into the G: backup folder beside the others.
3. **Teach `merge_clusters.py` to read video faces.** Today it reads photograph
   faces only, so a video-only cluster never merges with its person, and a video
   face that joined an unnamed sibling of a named group gets no name. Join
   `FACE-CLUSTERS-VIDEO.csv` to the embeddings in `faces.video.csv` on
   `(image, face_index)` - never a parallel file matched by position (learning
   45). Then re-run the merge and `build_db.py`.
4. `python stages\07_people\people_sheet.py --top 60`, then `python stages\07_people\verify_people_sheet.py`
   MUST exit 0 before Krish sees it: it checks every crop's `data-face` against
   the assignment files. Then give him round 4.

### Decided by Krish on 2026-09-15 (full text: `docs/ROADMAP.md`, Phase 8)

- **The game is a hosted page on a subdomain of krishraja.com** (Vercel project
  `krish-raja`), access-controlled. Not built yet.
- **Bharti enriches the Communal side only.** Her queue is every cluster whose
  newest answer is `needs_identifying = Bharti` (9 clusters, 449 Communal
  photographs); she is shown the Communal ones.
- **Communal will grow**: old photo libraries and digitised VHS are still to come.
- **Every video gets faces**, which is the chain running now.

### Next, in order

1. Finish naming: record Krish's round 10 answers, then keep the loop turning.
2. Build the game (roadmap Phase 8), starting with Bharti's queue.
3. Segment (Phase 4), reclaim (5), mirror to H: with server-side checksums (6),
   and only then purge Elements (7).

### Decided: the repository stays public (Krish, 2026-09-15)

Commit messages and docs name family members next to photograph counts. Krish
has seen that and said keep it public for now, no scrub. Do not reopen it, but do
not add anything more sensitive than that: the answers journal, face data and
anything the tripwire in `tools/publish_state.py` catches stay off GitHub.

### No Anthropic API is required, by design

Krish turned Anthropic access off on 2026-09-13 and nothing the chains run needs
it. Classification used Google Gemini; faces, verifiers, `build_db` and the video
pipeline are all local.

### The rule that now governs every long step

`Invoke-Step` in `guards/steps.ps1` makes five things mandatory:
`-Preflight`, `-Start`, `-Progress`, `-Postcondition` and **`-Verify`**.

`-Verify` must RE-DERIVE a sample of the output from its source and compare. It
must never inspect the output's shape. On 2026-09-13 a five-hour face run was
corrupt in a way where every row was well-formed, every vector had unit norm,
every count was plausible and the exit code was 0. **Validity is not
correctness.** Only recomputing the answer separates them.

`tests/test_chain_gating.py` fails the build if any chain launches a subprocess
outside `Invoke-Step`, or declares a step without a `-Verify`, or calls
`Invoke-Step` without loading it. Run the four test files before trusting a
change.

### Still true from earlier

- **Re-run the receipt sweep** now the library is fully classified. **Do not
  widen the pattern** - the next matches are a PAN card, an HMRC letter, a bank
  statement, a Form 1042-S. Those are identity records for
  `Archive\Personal\01-Identity\`, not a deletion sweep.
- **Photograph face coverage is sound.** Detection only opens photographs the
  classifier said contain a person; a random 300 of the rest had 0.7% confident
  faces, all statues and murals (2026-09-13). Videos are the exception, which is
  why the video chain looks at every frame.
- **`_Review`** has no agreed rule. A rule got this wrong once at 13,446 files.

### Do not

- **Re-run `cluster_faces.py --apply`.** It renumbers every cluster, and every
  answer in the journal points at a cluster id - each would silently land on
  somebody else. New faces go through `assign_video_faces.py`, which freezes them.
- **Write a human answer anywhere but `stages/07_people/answers.py`.** Everything else is
  derived and can be rebuilt for money or time. A person's judgement cannot.
- **Delete from Elements.** It is the only second copy until the H: mirror
  exists. D: (Boogles) has 3.7 TB free - there is no space pressure to relieve.
- **Run memory-hungry jobs beside the chain.** Something kills long jobs on this
  box under memory pressure. It can no longer corrupt anything, but it costs
  restarts.

----

## DONE: the drive migration (completed 2026-09-11, kept for the record)

The letters have been swapped and the copy is verified — `D:` is now the LaCie
`BOOGLES` (3.7 TB free) and `E:` is the Elements. The steps below are what was
run, kept because the verification argument in them is the one to reuse for the
H: mirror.

### The steps as they were run

**This session was handed over at the moment the library copy completed.** Everything
below is a command, in order, with what a pass looks like and what to do on a failure.
Nothing here needs improvising.

### Where you are

| letter | disk | role |
|---|---|---|
| `D:` | WD Elements, 931.5 GB, label `Elements` | the library, **still live**, and the source of the copy |
| `E:` | LaCie Rugged Mini, 4,657 GB, NTFS, label `BOOGLES` | the copy, and the permanent library once proven |

The letters swap at step 4. Until then, `D:` is the old disk and every tool is correctly
pointed at it. **Do not run the ingest before the swap** — it would write into a drive
that is about to become a frozen backup.

### Step 0 — confirm the copy actually finished

**Steps 1 and 2 may already be done.** A chained watcher was armed on 2026-09-11 at
13:30 to run them the moment the copy exits, because the copy and the verification
are both disk-bound and the only latency worth removing is the gap between one
finishing and somebody noticing. **Read `D:\_PhotoAudit\migrate-chain.log` first:**

- `VERIFIED.` — steps 1 and 2 are done. Go to step 3. **This is the state as of
  2026-09-11 19:45.** 73,197 of 73,198 files passed on the first pass; the one
  failure was a 7.7 GB file that copied to an IDENTICAL SIZE with different
  content, was re-copied, and now reads back matching the source. One bad write
  in 844 GB is bad luck; a second would make the dock or the new drive the
  suspect, so check for new mismatches rather than assuming.
- `STOPPED: ...` — it stopped deliberately and the line says why. Do not swap the
  drive letters, do not touch the source, fix what it names.
- only `waiting for the copy to finish` — the copy is still running, or the watcher
  itself was killed. Check for a `python.exe` process; if there is none and the copy
  log has no `copy finished` line, re-run the copy, it resumes.

The watcher does not survive a reboot. If it is gone, run steps 1 and 2 by hand -
they are the same two commands.

```powershell
Get-Content D:\_PhotoAudit\migrate.log -Tail 3
Get-Process python -ErrorAction SilentlyContinue
```

Expect `copy finished in N min` and no `python.exe`. If a python process is still
running, the copy is still going: leave it. If there is no process and no "finished"
line, it died — re-run the same command, it resumes from where it stopped:

```powershell
python -u D:\_PhotoAudit\scripts\migrate_library.py --to E: --apply
```

Launch it detached (`Start-Process pwsh -WindowStyle Hidden`); a tracked background task
gets killed by the memory watchdog (learning 9), which happened three times on
2026-09-10 and 11.

### Step 1 — prove the copy

```powershell
python -u D:\_PhotoAudit\scripts\migrate_library.py --to E: --verify
```

Reads every file on `E:` and compares it to the hash taken from the bytes as they were
written. ~2.5 hours. Writes `MIGRATION-VERIFY.csv`, prints an OK / MISMATCH / MISSING
tally, and exits non-zero on any failure.

**On any failure: stop. Do not swap the letters, do not delete anything, do not touch
the source.** Report the mismatching files. A file that failed to copy is recoverable
while the source is untouched and irrecoverable once it is not.

### Step 2 — carry the working directories across

```powershell
python -u D:\_PhotoAudit\scripts\migrate_library.py --to E: --extras --apply
```

`_PhotoAudit` (395 files), `_enrichment` (37), `_thumbs` (15,794) — about 0.67 GB, a
couple of minutes, each file verified as it lands. Run it **after** step 1 so the
verification report travels with it.

`_PhotoAudit` is not optional. It holds the journals, the H: resume set, every ingest
report, the hash cache and the origin map, and every tool in the kit opens
`D:\_PhotoAudit` by absolute path. Without it on the new volume, the next ingest
re-pulls everything and the resume logic silently has nothing to read.

### Step 3 — ask Krish to swap the drive letters

**This needs an elevated shell and cannot be done from an agent session.** Give him the
disk numbers from `Get-Partition` — address disks by NUMBER, never by letter, because
the letters are the thing being changed:

```powershell
Get-Partition | Where-Object DriveLetter | Format-Table DiskNumber,PartitionNumber,DriveLetter,Size
# then, with <lacie> and <elements> filled in from that output:
Set-Partition -DiskNumber <lacie>    -PartitionNumber <n> -NewDriveLetter T
Set-Partition -DiskNumber <elements> -PartitionNumber <n> -NewDriveLetter E
Set-Partition -DiskNumber <lacie>    -PartitionNumber <n> -NewDriveLetter D
```

This is the entire repointing. No code changes: every path in the kit is either `D:` or
derived from `guards/paths.py`.

### Step 4 — prove the swap, before anything writes

```powershell
python D:\_PhotoAudit\scripts\postswap_check.py
```

Eight checks: that `D:` is now the 4,657 GB disk, that the four chronology trees exist
under it, that the file count matches the migration's own record, that the audit trail
arrived, that recent journalled placements resolve, that the H: resume set rebuilds,
that a second copy of the library still exists on another volume, and that `STATE.json`
is not reporting zero.

It exits non-zero on any failure. **This is the one step in the migration with no error
message of its own:** every path in the toolkit is `D:\...`, so if the wrong disk
answers to D: the tools do not fail, they operate on the wrong drive quietly.

### Step 5 — recount, then finish the ingest

```powershell
python C:\Users\krish\dev\contentarchives\tools\track.py --print
python -u D:\_PhotoAudit\scripts\ingest_from_h.py --all --apply   # detached
```

Only `from-wd6400` remains: 100.8 GB to pull, 77.9 GB certainly new. The run opens by
printing how many files it will not re-pull. Afterwards check `H-COPY-FAILURES.csv` —
if it exists and is non-empty, those files are not in the library and nothing else will
say so.

### The sheet everything feeds — `MASTER.csv`

Krish, 2026-09-11: *"getting that sheet to be 100% is going to be the mission of the
game, the image recognition, and all other work done to figure out as much info about
the content as possible."* So there is one sheet, it is generated, and it has a score.

```powershell
python C:\Users\krish\dev\contentarchives\stages\08_index\master_sheet.py
```

One row per file in the library, 73,198 of them, written to `D:\_PhotoAudit\MASTER.csv`
and regenerated by `tools/refresh.py` along with everything else. Identity, provenance,
technical metadata and every model or human judgement, in one place.

**It could not be built until 2026-09-11, and the reason is worth knowing.** The
inventory is keyed on path; the enrichment store is keyed on content hash; and
`INVENTORY.csv` had no hash column. There was no join. Every classification run was
filling a store that nothing could read back against the library.

The key came from the migration. `migrate_library.py` hashed every file as it copied
it, and `store.content_hash()` is the same computation — blake2b, 32-byte digest,
whole file — so `MIGRATION-HASHES.csv` is a complete, verified path-to-hash map for all
73,198 files, agreeing with the store by construction rather than by luck. It is seeded
into `HASH-INDEX.csv` and maintained incrementally: a new file is hashed once and
remembered, so a fresh ingest costs its own bytes rather than the whole library.

**Coverage as of 2026-09-11, before the classification pass: 59.2%.**

| field | coverage | |
|---|---|---|
| Hash, Side, Bytes, Ext | 100% | identity is solved |
| OriginFolder, SourceRoot, OriginPath | 94.9% | provenance |
| Duration | 89.5% of videos | |
| Year, Month | 87.9% | |
| Width, Height | 59.9% | |
| DateTaken | 56.5% | old scans have no EXIF and never will |
| Make, Model | ~44% | |
| kind, people, subject, keep | 21.5% | the 2026-09-08 Haiku pass over `_Review` only |
| sensitivity, setting, era | **0%** | those fields postdate that pass |

Two joins were silently broken when the sheet was first assembled, and both read as
missing data rather than as bugs. `OriginPath` reported 0% against 110,652 origin rows,
because that file stores relative pre-restructure paths and `paths.resolve()` — written
for exactly this — was never called. `Duration` reported 14%, because it was scored
over the whole library rather than over videos; it is 89.5% of the files it can apply
to. Coverage denominators are now per-field.

`Lat`, `Lon` and `place` are marked **opportunistic** and excluded from the target: a
camera either wrote a geotag or it did not, and a metric whose 100% is unreachable by
construction is not a mission, it is a reproach.

**The classification pass is the single biggest lever on that number** — it fills eight
columns for every file in the chronology, taking four of them from 21.5% toward 100%
and three of them from zero.

---

### Step 6 — the classification pass

Approved by Krish: **Gemini 3.1 Flash-Lite**, ~$20.70 for 91,394 calls. Chosen on a
reference no model wrote (`stages/05_enrich/consensus.py`); see "Where things stand". Do not
substitute a cheaper model without re-reading learning 35.

### Still open, and explicitly not done

- **Five identity documents** sit in `Media\NoDate\` — `passport` x3, `citizenship`,
  `visa`. `move_identity_docs.py` files them into `Archive\Personal\01-Identity\`. Not
  moved on 2026-09-11 because the migration was walking that tree.
- **The cloud copy does not exist.** H: holds source material, not a mirror. See
  "The remaining work" section 3 — verification there must use Drive's server-side
  `md5Checksum`, never a read-back through the mount.
- **51 derived copies** in the chronology (`DERIVED-IN-CHRONOLOGY.csv`) and **14.88 GB
  of hash-confirmed cross-tree duplicates** (`XTREE-DUPLICATES.csv`). Nothing moved or
  deleted in either case; both are segmentation judgements for Krish.

### If you are picking this up cold

**The repo is not a complete copy of the toolkit, and the gap is bigger than it
looks.** There are 103 Python scripts on the machine at `D:\_PhotoAudit\scripts\` and
71 in the repo. `publish_scripts.py` is a curated list, not a mirror.

**Four are blocked by the publication tripwire, and it is right to block them** - each
either contains the identity vocabulary it exists to match, or real personal data:

- `route_h.py` — routes a file to chronology, production or archive before it enters
  the library. Blocked on `passport`, `birth cert`, `oci`, `payslip`, `tax return`.
- `move_identity_docs.py` — lifts identity scans out of the chronology. Blocked on
  eleven terms including `nhs`, `p60`, `prescription`, `mortgage`.
- `provenance.py` — carries real source-folder names in a hardcoded list.
- `publish_scripts.py` — contains the tripwire term list, so it matches every term
  there is and can never publish itself.

Redacting any of them would rewrite the rule into nonsense. **If you need one, read it
on the machine.**

**The other 41 are one-offs** - a script written for one folder on one evening, kept
because nothing here is thrown away but not worth carrying as a toolkit. Examples:
`3-Build-Library.py`, `aa_compare.py`, `analyse_lorimer.py`, `analyse_only.py`, `biggest_review.py`, `check_downloads.py`. If the remaining work needs one, it is on the machine;
add it to `KEEP` in `publish_scripts.py` and re-run with `--apply`.

Everything the documented remaining work depends on **is** in the repo, including the
segmentation pair `propose_split.py` and `apply_split.py`, which were missing until
2026-09-11 and are the whole of step 2.

Everything above is checkable rather than believable. `Get-Volume` tells you the
letters. `Get-Content D:\_PhotoAudit\migrate.log -Tail 5` tells you the copy's position.
`python tools/audit_previous_session.py` grades the previous session against the
filesystem. Nothing in this section should be trusted over what those report.


## Where things stand (2026-09-11)

Counted from disk by `tools/track.py` at 2026-09-11T11:31, not narrated.

```
D:\ContentLibrary\                     73,198 files    844.1 GB total
  Media\Personal\YYYY\YYYY-MM\         51,900          468.0 GB   the chronology
  Media\Communal\YYYY\YYYY-MM\          3,791           22.5 GB   family and shared
  Media\Pending-Segmentation\           6,215          205.6 GB   ingested, no side yet
  Media\NoDate\                         2,876          109.8 GB   date never established
  Archive\ ContentProduction\ _Review\  ~8,400           38.3 GB

D: 26.9 GB free of 931.5   (full, by design - see RIGHT NOW above)
```

**`NoDate\` has grown to 109.8 GB across 2,876 files** and is now the second largest
tree. That is the `from-wd6400` childhood-PC material arriving without usable dates,
and it is a segmentation input, not a problem: a 1998 scan has no EXIF and never will.

**The 2026-09-07 Takeout export is fully ingested and verified** — all six parts,
35,114 media members, each matched against its archive's central directory before that
archive was deleted. `verify_takeout_complete.py` re-runs any time.

**The H: pull is nearly done and fully resumable.** `from-lorimer`, `from-dji-2026`,
`from-gopro-2024`, the phone backup and the small folders are all in. Only
`from-wd6400` remains: 100.8 GB to pull, of which 18.8 GB is near-certain duplicate,
4.1 GB shares a size only, and **77.9 GB is certainly new**. The resume set is read
from the append-only journals AND from the per-batch `INGEST-*.csv` reports, so
duplicates and sub-20 KB skips are not re-fetched either - that fix alone saved
31.18 GB of re-transfer.

**Capacity is resolved by hardware, not by pruning.** The finished library projects to
922.0 GB against Elements' 931.5 GB - it fits by 9.5 GB, which is unusable because the
ingest needs a 40 GB floor plus a 20 GB stage. The LaCie is 4,657 GB. Reclaim on
Elements was measured and exhausted: 318.9 GB of what a folder listing calls duplicate
is hardlinks that free nothing, ~39 GB is sole-copy, and every scratch directory
together is 1.3 GB. Compression was measured and abandoned at ~83 GB, less than the
shortfall even if it were free.

**A file that cannot be copied is not a log line.** `DJI_20260623150233_0097_D.MP4`,
3.95 GB, failed `[WinError 1450] Insufficient system resources` on two separate runs a
week apart - deterministic, not transient, because `shutil.copy2` asks the Drive mount
for one transfer it cannot service. It now retries in 8 MB chunks; that file is in the
library, verified by size and hardlinked. Anything that still fails is named in
`H-COPY-FAILURES.csv`, which does not exist because nothing has.

**A missing tree must be an error, never a zero.** Both copies of `track.py` walked
`Library/` and `NoDate/` off the ContentLibrary root - names that stopped existing at
the restructure - and `os.walk` on a missing directory yields nothing and raises
nothing, so `PROGRESS.md` reported a 61,678-file library as **0 files** for two days.
Learning 34. `migrate_library.py` then did the same thing for a different reason a day
later, which is why both now refuse to continue on an empty result.

**The dedup index now covers `Archive\` and `ContentProduction\`.** It did not, while
`ingest_tree --dest-root` writes into both, so four videos were held twice. Three were
byte-identical (14.88 GB); the fourth shares a filename AND an exact byte count with
its twin and has **different content** - learning 36, and the reason the reclaim figure
is the hash-confirmed 14.88 GB rather than the 22.09 GB the inode check suggested. The
cache now records which roots it was built over, because it is keyed on the row count
of `autopilot-added.csv` and could not otherwise notice the root list changing.

**Nothing is deleted without a proven surviving copy.** `guarded_delete.py` is the only
sanctioned path: different inode, equal size, blake2b-256 re-hashed at the instant of
the unlink, survivor readable to its last byte - or membership of a deliberately tiny
garbage list that excludes screenshots.

### New, not yet ingested: the WD6400 childhood-PC drive (2026-09-06)

**17,102 files / 140.62 GB** are staged and verified at
`H:\My Drive\_photo-consolidation\from-wd6400\`, one file per distinct content, each
proven at rest by Blake2b-256. They are **not in the library yet**.

Full account: [`docs/rescues/2026-09-06-wd6400.md`](docs/rescues/2026-09-06-wd6400.md).
It earned learnings 22, 23 and 24 — read those before writing any dedupe or skip logic
against this set.

Before touching it:

- **The source drive still exists and must not be destroyed** until Google Drive
  reports sync complete. At-rest verification proves the bytes are right *in the Drive
  mount*, not that they reached the cloud — and the mount was measured running ahead of
  the cloud.
- Ingest by the hashes in that folder's `push-manifest.csv`; do not re-read 140 GB.
- The set is already internally deduplicated. It is **not** deduplicated against
  `D:\ContentLibrary` — re-measured 2026-09-10: 95.3 GB matches no size in the library at
  all, 30.9 GB shares a name AND a size with something held, and 14.4 GB shares a size
  only, which is a hint and not a verdict.
- Its folder names are actively misleading; the rescue doc has measured examples.

---

## FIRST, ALWAYS: measure the link

Every remaining task is bandwidth-bound, and every throughput guess made on this
project before measuring has been wrong (learnings 10 and 15).

```powershell
netsh wlan show interfaces | Select-String "SSID|Band|Radio type|Signal"
Get-NetAdapter | Select-Object Name, Status, LinkSpeed
$sw=[Diagnostics.Stopwatch]::StartNew()
$r=Invoke-WebRequest "https://speed.cloudflare.com/__down?bytes=10000000" -UseBasicParsing
$sw.Stop(); "{0:N2} MB/s" -f (($r.RawContentLength/1MB)/$sw.Elapsed.TotalSeconds)
```

On 2026-09-06 this measured **1.5 Mbps** on a 2.4 GHz Wi-Fi extender with a 1 Gbps
Ethernet port sitting unplugged. On 2026-09-07, wired, it measures **220-425 Mbps
sustained** — a 150-280x improvement. Re-measure anyway: the point of this section is
that every throughput guess made before measuring has been wrong, and that does not
stop being true once one measurement came back good.

---

## The remaining work

The phased plan through to the end state is [`docs/ROADMAP.md`](docs/ROADMAP.md). The sections below are the near-term detail.

### 1. Finish the H: pull — only `from-wd6400` remains

100.8 GB left to pull, **77.9 GB of it certainly new**. Everything else on H: is in.

```powershell
python -u D:\_PhotoAudit\scripts\ingest_from_h.py --all          # dry run, prints what it will skip
python -u D:\_PhotoAudit\scripts\ingest_from_h.py --all --apply
```

Launch detached (`Start-Process pwsh -WindowStyle Hidden`) — a tracked background task
gets killed by the memory watchdog (learning 9), which happened twice on 2026-09-11.

**Do not start this until the drive migration is finished.** One thing at a time when
the disk is the constraint.

Re-running is cheap and safe. The run opens by printing how many files it will not
re-pull and how many hours that saves, halts by design at 40 GB free on the library
volume, keeps every batch already ingested, and continues where it stopped.

Afterwards, check `H-COPY-FAILURES.csv`. If it exists and is non-empty, those files are
not in the library and nothing else will say so.

### 2. Segment `Pending-Segmentation\` — 6,215 files, 205.6 GB with no side assigned

Everything a fresh ingest adds lands in `Media\Pending-Segmentation\` by design. It has
to end up in `Personal\` or `Communal\`, or in `_Review\` if it is not a memory at all.
The user's standing requirement (2026-09-08): the chronology holds personal memories
and nothing else, the split is audited rather than assumed, and screenshots do not
live in it.

**The enrichment model is settled by measurement, and the first measurement was
circular.** Bake-off over a stratified 300-file sample, 50 each of photo / document /
screenshot / graphic / meme / poster, with every verdict written to
`D:\_enrichment\bakeoff-verdicts.csv`. The full pass is **91,394 model calls** —
51,774 images plus 9,905 videos at 4 sampled frames each — counted by `job_calls()`
rather than the literal 116,500 that used to be multiplied into every headline cost.

`bakeoff.py` scores agreement against the labels already in the store. Those labels
are Haiku's, so Haiku was being asked how often it agrees with itself, and every other
model was being scored on how far it diverges from one particular model's opinion.
`stages/05_enrich/consensus.py` rebuilds the reference per file from the majority of the OTHER
models, excluding whichever model is being scored. A label two independent models
agree on is not truth, but it is evidence that does not come from the model on trial.

| model | vs independent consensus | non-memories called "photo" | $/1,000 | full pass, batched |
|---|---|---|---|---|
| **Gemini 3.1 Flash-Lite** | **87.8%** | **3 of 168 (2%)** | $0.453 | **$20.70** |
| Gemini 3.5 Flash-Lite | 87.5% | 5 of 170 (3%) | $0.589 | $26.92 |
| GPT-5 mini | 81.5% | 22 of 178 (12%) | $0.269 | $12.29 |
| Claude Haiku 4.5 | 74.5% | 3 of 172 (2%) | $1.133 | $51.77 |
| GPT-5 nano | 57.9% | 79 of 178 (44%) | $0.060 | $2.74 |

The second column counts the only error that costs anything here: a screenshot, meme,
document or graphic filed into the chronology as a photograph, which a human then has
to find and pull back out.

- **nano is not a cheaper classifier, it is a model with one answer.** It replied
  "photo" for 162 of 300 files in a sample that is 17% photographs, scoring a perfect
  50/50 on photos by saying "photo" to nearly everything.
- **Haiku is second-worst on accuracy and the most expensive**, at 2.5x Gemini 3.1 for
  13 points less agreement. It measured $1.133/1,000 against the ~$0.75 the price
  table implied. Re-tested 2026-09-10 at Krish's request; the case against it is not
  the earlier HTTP 401, which was a reporting bug, but the numbers above.
- **Roughly a quarter of the labels already in the store are wrong.** They score 75.5%
  against the same reference, and Haiku re-run scores 74.5% — stably mediocre rather
  than drifting. The pass is a replacement, not a re-derivation.
- **3.5 Flash-Lite is a tie with 3.1 on quality and 30% dearer.** No argument for it.

**Recommendation: Gemini 3.1 Flash-Lite, $20.70 batched.** Best on both columns and
2.5x cheaper than the incumbent.

Read the caveat with the table: a majority vote among models favours whatever those
models share, so it is evidence and not ground truth. It is simply the only measure
here that does not ask a model how often it agrees with itself — which is what
produced Haiku's apparent 100% and its actual 88.7%.

**Derived copies were reaching the chronology, and 51 are already in it.** The router
treats a camera filename as strong positive provenance that outranks weaker signals —
correct reasoning, wrong answer for a re-encode, which inherits the camera name of the
file it was made from. `content production & podcasts` on H: holds three
`DJI_<stamp>_youtube_720p.mp4` exports whose 4.6-5.0 GB originals are already held,
and the bytes differ so dedup cannot catch them either.

Fixed 2026-09-10 at the tier learning 29 says to fix it at: a name that *declares*
itself derived beats a camera name inferred from a prefix. `route_h.DERIVED` matches
an export marker only as a trailing segment introduced by `-` or `_`
(`_youtube`, `_proxy`, `_1080p`, `-converted`, `_export`, `_web`, ...), so
`Cannes 4k trip/IMG_2201.JPG` still routes to the chronology. Destination is
`production`, which is reversible and journalled — the asymmetry is the point.

Already admitted: **51 files, 2.6 GB**, mostly from the `from-lorimer` pull as
path-flattened Downloads. Five have their camera original held alongside; all of them
are paired with sizes in `D:\_PhotoAudit\DERIVED-IN-CHRONOLOGY.csv`. **Nothing was
moved** — some are `dji_export_..._editor.mp4`, edits the user made rather than
machine transcodes, and that is a judgement for the segmentation pass, not a rule.

### 3. Back up — being fixed, for the first time

Until 2026-09-11 the library had exactly one copy, on a USB drive that had logged 14
controller errors in a day. The migration ends that: Elements keeps a complete copy of
the library as of today while the LaCie becomes the working volume.

The agreed end state, decided with Krish on 2026-09-11:

- **LaCie (`BOOGLES`, 4,657 GB)** — the permanent local library. It absorbs the
  remaining 78 GB and has ~3.7 TB of headroom.
- **Elements (931.5 GB)** — left **untouched**, including its 20 years of raw source
  folders. Their names carry provenance the origin map cannot fully reconstruct, and a
  second copy nobody has edited is worth more than a tidy one somebody has.
- **H: (Google Drive)** — to become the offsite copy. **It is not one yet.** Today H:
  holds the *source* material, `_photo-consolidation`, and no library mirror.

Three things make the cloud copy real work rather than a checkbox, and all three are
already-paid-for lessons:

1. **~23 hours of upload** at the 10.5 MB/s this account measured for download. Upload
   has not been measured; measure it (learning 10) rather than assuming symmetry.
2. **The quota is unknown.** `Get-Volume` on H: reports the local cache volume, not the
   account (learning 17). Get the real figure from the Drive API. The library is
   844.1 GB now and 922.0 GB finished, and 371 GB of source folders are still up there.
3. **Verifying it is the hard part.** Do not hash through the mount: it hangs with zero
   bytes read rather than failing (learning 15), and reading a placeholder hydrates it
   and fills C: (learning 5). Learning 25 is a run that verified 17,102 of 17,102 files
   against a cloud mount having compared local bytes with local bytes. **Use Drive's
   `md5Checksum` field**, computed server-side, against a locally computed MD5. The file
   is never read back.

Krish's standing instruction: `ContentLibrary\` may be removed from Elements **only**
once it is verified on the LaCie *and* verified in the cloud. Note the arithmetic
before planning around the space it returns: roughly 319 GB of the library is
hardlinked to originals in the source folders that are staying, so deleting the library
tree frees about **525 GB, not 844**. Same illusion as learning 28, pointed the other
way. There is no pressure to do it at all — three copies at zero marginal cost is a
better posture than two.


## Waiting on the user — do not act unprompted

- **Five identity documents are still in the chronology**, all in `Media\NoDate\`,
  flagged by `passport` x3, `citizenship` x1 and `visa` x1 (50-230 KB scans). The
  schema puts these in `Archive\Personal\01-Identity\` and `move_identity_docs.py`
  does it. Not moved on 2026-09-11 because the migration was walking that tree, and
  moving a file under a running copy is how it ends up in neither place. **This was
  a vacuous PASS until 2026-09-11**: `audit_previous_session.py` checked the
  pre-restructure paths, found nothing in directories that do not exist, and
  reported "none remain". A check that cannot fail is not a check.
- **`D:\ContentLibrary\_Review\`** — 5,844 files (1.4 GB) judged not-a-memory.
  Nothing was deleted. The user reviews and empties it. The count fell from 10,540
  because the 2026-09-08 vision pass found 9,975 real memories the rules had swept
  out and restored them — a rule that evicts on a filename pattern will do this again.
- **`D:\ContentLibrary\Archive\99-Unsorted\`** — origins whose *side* is not established, plus
  messenger stickers. Keep it; it is the pressure valve that stops things being
  forced into a wrong category.
- **`Media\Pending-Segmentation\` (6,215 files, 205.6 GB)** — origins with no side
  assigned. Deliberately left in place rather than defaulted to Personal. This is the
  queue for step 2, and every fresh ingest adds to it.

---

## Decisions already made — do not reopen

| Decision | Why |
|---|---|
| Chronology splits Personal / Communal, by **origin folder** | 74,000 file judgements become a few hundred folder judgements |
| A family member's device inside the user's own storage is **communal** | whose device it is decides the side, not whose storage it sat in |
| Archive mirrors that split, work inside `Personal\` | a parent's passport is exactly what you hand over, or hold back, as a batch |
| A classifier may **move** a file, never delete one | uncertain files stay in the chronology on purpose |
| `H:` stages oversized and cross-machine files; becomes D:'s mirror **only after** the audit | mirroring an unaudited library propagates its mistakes |
| Repo is public; folder-level origin map published, per-file map stays local | the per-file map leaks through filenames |
| Compression **abandoned** | measured: grainy footage has a quality ceiling, 4K HEVC ran at 0.1× realtime |
| Downloads go to `C:`, never `D:` | D: corrupts partial files under parallel write |
| Large videos are all kept | precious memories and travel footage |
| Add storage rather than prune or compress to fit (2026-09-10) | measured: 242.8 GB still to come against 146.4 GB of headroom; reclaim on D: is exhausted and compression is worth less than the shortfall |
| The LaCie (4,657 GB) is the permanent local library; Elements becomes a frozen copy (2026-09-11) | the finished library projects to 922.0 GB against Elements 931.5 GB - it fits by 9.5 GB, and the ingest needs a 40 GB floor plus a 20 GB stage to run at all |
| Elements keeps its 20 years of raw source folders, untouched (2026-09-11) | the folder names carry provenance the origin map cannot reconstruct, and an unedited second copy is worth more than a tidy one |
| `ContentLibrary` may leave Elements only after BOTH the LaCie copy and a cloud copy are verified (2026-09-11) | Krish: "no need for elements to contain the contentlibrary once that is safely on Boogles and H drive cloud backup verified and safe" |
| Gemini 3.1 Flash-Lite classifies the library (2026-09-10) | best on agreement against an independent reference (87.8%) AND on chronology contamination (2%), at 2.5x less than Haiku |

**The data-loss topic is closed.** 45 files were lost early in this project. Do not
re-narrate it. The rules it produced still bind — LEARNINGS 1 and 2.

---

## Standing constraints

- **Push to `main` by default.** Krish gave standing approval on 2026-09-11: commit
  and push in the same motion, do not stop to ask each time. The canon in
  `AGENTS.md` requires explicit approval before publishing; this is that approval,
  given in advance, for this repository and this branch. It covers the *asking*, not
  the *verifying* - still run the redaction tripwire on anything published, scan the
  diff for key-shaped strings, and read the diffstat before pushing. Ask again for
  anything the grant plainly does not cover: a force push, a history rewrite, a new
  public repository, or a branch that is not `main`.
- **Pull and merge, never force.** Other machines write to this repo. A push was
  rejected on 2026-09-11 because a steward run had landed; the fix was to merge and
  keep both sides, not to overwrite. Nine commits sitting local is not a safe state:
  this repo IS the handover, and an unpushed commit is one another agent cannot see.
- **Progress lives in data, not conversation.** Regenerate state; never assert it.
- Nothing built should be throwaway — the toolkit gets reused on other machines, on
  old phone backups, and on digitising a family member's VHS tapes.
- One thing at a time when bandwidth or the disk is the constraint.

---

## Finishing a session

```bash
python tools/refresh.py
python tools/check_manifest.py
git add -A && git commit -m "Update state" && git push
```

Commit state even mid-task — **especially** then. And **update the "Where things
stand" section above**, or the next session starts from a description that has
already drifted. That is not hypothetical: this file described `_Staging` as holding
194 files awaiting judgement hours after it had been emptied and deleted.

If something was learned the hard way, add it to `LEARNINGS.md` with the incident
that produced it. The incident is what makes the rule stick.
