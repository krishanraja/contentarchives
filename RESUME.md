# RESUME PHOTOLIBRARY

**You have been asked to resume the media consolidation.**

> **Machine state first.** A drive migration is part-done and the drive letters
> moved on 2026-09-11. Read [RIGHT NOW](#right-now-finish-the-drive-migration-handover-point-2026-09-11)
> before running any command in this file, including the ones directly below.

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

## RIGHT NOW: finish the drive migration (handover point, 2026-09-11)

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
derived from `scripts/paths.py`.

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

### Step 6 — the classification pass

Approved by Krish: **Gemini 3.1 Flash-Lite**, ~$20.70 for 91,394 calls. Chosen on a
reference no model wrote (`engine/consensus.py`); see "Where things stand". Do not
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
