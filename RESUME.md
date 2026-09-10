# RESUME PHOTOLIBRARY

**You have been asked to resume the media consolidation.**

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

---

## Where things stand (2026-09-10)

Counted from disk by `tools/track.py` at 2026-09-10T14:50, not narrated.

```
D:\ContentLibrary\
  Media\Personal\YYYY\YYYY-MM\        51,900    468.0 GB   the chronology
  Media\Communal\YYYY\YYYY-MM\         3,791     22.5 GB   family and shared
  Media\Pending-Segmentation\          4,554    148.5 GB   ingested, no side yet
  Media\NoDate\                        1,433      7.3 GB   date never established
                                      ------    ---------
                                      61,678    646.2 GB

  Archive\                             1,996      7.3 GB
  ContentProduction\                      18     25.5 GB
  _Review\                             5,844      1.4 GB   not-a-memory. NOT deleted.

D: 186.1 GB free of 931.5    C: 161.6 GB free
```

**The 2026-09-07 Takeout export is fully ingested and verified** — all six parts,
35,114 media members, each matched against its archive's central directory before
that archive was deleted. `verify_takeout_complete.py` re-runs any time.

**The H: pull is part-done and now genuinely resumable.** `from-lorimer` and
`from-dji-2026` are in; `from-gopro-2024` is in progress. Until 2026-09-10
`ingest_from_h.py` rebuilt its batch list from a full folder scan on every run, so
resuming after an interruption re-pulled everything already ingested — 86.4 GB, or
2.4 h at the measured 10.5 MB/s. It now skips on `(relpath, size)` read from the
append-only journals. Not from the per-batch `INGEST-*.csv` reports: those were being
written to one filename per folder, so batches 1-3 of DJI are simply gone from them.

**D: cannot hold the finished library, and this is now measured rather than assumed.**
380.5 GB remains on H:, of which 118.9 GB is near-certain duplicate (name and size
both already held), 18.7 GB shares a size only, and **242.8 GB is certainly new**
against **146.4 GB of usable headroom** (186.1 free, less the 40 GB batch floor). The
2026-09-07 claim that the end state "plausibly fits the existing drive" was true when
the library was expected to land near 540 GB; it is already at 646.2 GB with a third
of the input still outside it. Reclaim on D: is exhausted: 318.9 GB of what a folder
listing calls duplicate is hardlinks that free nothing (learning 28), 39.2 GB is
sole-copy, and every scratch directory together is 1.3 GB. Compression was measured
and abandoned at ~83 GB, which is less than the shortfall even if it were free.
**The user chose to add a drive (2026-09-10).** The ingest is expected to halt cleanly
at the floor with `from-boogles` and `from-wd6400` untouched; the resume logic makes
continuing into new storage a `paths.py` edit and a re-run.

**A file that cannot be copied is not a log line.** `DJI_20260623150233_0097_D.MP4`,
3.95 GB, failed with `[WinError 1450] Insufficient system resources` on two separate
runs a week apart — deterministic, not transient. `shutil.copy2` asks the Drive mount
for one transfer it cannot service. It now retries in 8 MB chunks, and any file that
still fails is written to `H-COPY-FAILURES.csv` rather than scrolling past in a log.

**A missing tree must be an error, never a zero.** Both copies of `track.py` walked
`Library/` and `NoDate/` off the ContentLibrary root — names that stopped existing at
the restructure. `os.walk` on a directory that does not exist yields nothing and
raises nothing, so `PROGRESS.md` reported a 61,678-file library as **0 files** for two
days, under a header promising every figure is counted from disk. Both now count the
roots in `paths.py` and refuse to run if a chronology tree is absent.

**The dedup index cache was 19,096 entries ahead of the disk** — 80,774 cached against
61,678 present, because it is only replayed from `autopilot-added.csv` while the
restructure, the `_Review` eviction and the dedup reclaim all MOVED files. Learning 27
already makes the dangerous direction safe: a stale candidate hashes to `None`, is
counted, and is skipped rather than declared a match. But it silently *misses*
duplicates, which is unaffordable at this disk pressure. Pickle retired 2026-09-10;
delete it after anything that moves library files.

**Nothing is deleted without a proven surviving copy.** `guarded_delete.py` is the
only sanctioned path: different inode, equal size, blake2b-256 re-hashed at the
instant of the unlink, survivor readable to its last byte — or membership of a
deliberately tiny garbage list that excludes screenshots.

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

### 1. Finish the H: pull — 380.5 GB remaining, and it will not fit

`from-lorimer` and `from-dji-2026` are in. Remaining, in `PRIORITY` order:

| folder | remaining | certainly new |
|---|---|---|
| `from-gopro-2024` | 25.7 GB | 24.2 GB |
| `Krish - Phone Backup - Jun to Sep 2025` | 176.0 GB | 114.4 GB |
| `content production & podcasts` | 2.2 GB | 0.4 GB |
| `from-personal-google-drive` | ~0 | ~0 |
| `from-boogles` | 31.6 GB | 4.5 GB |
| `from-wd6400` | 140.6 GB | 95.3 GB |

```powershell
Set-Location D:\_PhotoAudit
python -u scripts\ingest_from_h.py --all            # dry run: prints what it will skip
python -u scripts\ingest_from_h.py --all --apply
```

Launch detached (`Start-Process pwsh -WindowStyle Hidden`) — a tracked background task
gets killed by the memory watchdog (learning 9).

Re-running is now cheap and safe: the run opens by printing how many files it will not
re-pull and how many hours that saves. It halts by design at 40 GB free on the library
volume, keeps every batch already ingested, and continues where it stopped.

**The phone-backup folder grew.** `H-INVENTORY.csv` (2026-09-08) records it at 966
files / 0.7 GB. It is now 3,110 files / 176.0 GB — the user kept uploading. Re-scan
before trusting any inventory of H:; do not plan from the stored one.

**Expect a halt around `from-boogles`.** There is 146.4 GB of headroom for 242.8 GB of
new content. When it stops, that is the design working, not a failure. The fix is
storage, which the user has agreed to add. To continue into it: change `ROOT` in
`paths.py` and re-run the same command — `STAGE`, the journals and the free-space
floor all derive from it now, and the resume set is read from the journals, so nothing
already ingested is fetched twice.

**One file needs a second pass.** `DJI_20260623150233_0097_D.MP4` failed to copy on
both prior runs. The chunked fallback landed after the DJI folder had already been
walked in the current run, so re-run `--folder "from-dji-2026 (cannes and wedding)"
--apply` once the main pull is done; the resume set reduces it to that one file. Check
`H-COPY-FAILURES.csv` afterwards — if it is non-empty, those files are not in the
library and nothing else will say so.

### 2. Segment `Pending-Segmentation\` — 4,554 files, 148.5 GB with no side assigned

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
`scripts/consensus.py` rebuilds the reference per file from the majority of the OTHER
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

### 3. Back up — the largest open risk

There is still no second copy. Capacity is **not** the constraint: `H:` is a 2 TB
account with ~1.65 TB free against a ~500 GB library. The mount *reports* ~133 GB
because `Get-PSDrive` returns the local cache volume (learning 17).

Back up **`ContentLibrary\`** — `Media\`, `Archive\` and `ContentProduction\`. Not the whole
drive, or the 320 GB of hardlinked bytes uploads twice.

**Batch it.** Drive for Desktop stages uploads through a cache on `C:`, so one giant
copy fills the system drive and dies partway. Check `C:` free space between batches.

The user's standing instruction was not to mirror before the audit. Raise it rather
than assume: the audit is now substantially done, and an unbacked library on a drive
throwing controller errors is the larger risk.

---

## Waiting on the user — do not act unprompted

- **`D:\ContentLibrary\_Review\`** — 5,844 files (1.4 GB) judged not-a-memory.
  Nothing was deleted. The user reviews and empties it. The count fell from 10,540
  because the 2026-09-08 vision pass found 9,975 real memories the rules had swept
  out and restored them — a rule that evicts on a filename pattern will do this again.
- **`D:\ContentLibrary\Archive\99-Unsorted\`** — origins whose *side* is not established, plus
  messenger stickers. Keep it; it is the pressure valve that stops things being
  forced into a wrong category.
- **`Media\Pending-Segmentation\` (4,554 files, 148.5 GB)** — origins with no side
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

**The data-loss topic is closed.** 45 files were lost early in this project. Do not
re-narrate it. The rules it produced still bind — LEARNINGS 1 and 2.

---

## Standing constraints

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
