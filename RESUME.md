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

## Where things stand (2026-09-06, late)

```
D:\PhotoLibrary\
  Personal\YYYY\YYYY-MM\    56,928   the chronology
  Communal\YYYY\YYYY-MM\     3,796   family and shared
  NoDate\                      853   date never guessed
  Library\                     328   origins with no side assigned yet
  _Review\                  10,540   classified not-a-memory. NOT deleted.

D:\Archive\                    1,988
  Personal\   01-Identity 02-Financial 03-Property 04-Medical 05-Education 06-Work
  Communal\   01-Identity 02-Financial 03-Property
  99-Unsorted\ side or category not established

D:\ContentProduction\             18   podcast, TV interview, 2026 videos, exports

D: 312 GB free (was 172 GB)
```

`_Staging` no longer exists — everything in it was filed.

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
Ethernet port sitting unplugged. The user planned to move to 5 GHz and wired on
2026-09-07. **If it still reads ~1.5 Mbps the change did not take — say so, and do
not start the transfers.**

---

## The remaining work

### 1. Finish the second machine's batch — 744 files

781 of 1,525 are staged at `D:\_lorimer_stage`; all of those are ingested. The
remaining 744 are only on the Drive mount.

```powershell
robocopy "G:\My Drive\_photo-consolidation\from-lorimer" "D:\_lorimer_stage" /E /R:2 /W:5 /NP /NFL /NDL /MT:8
python D:\_PhotoAudit\scripts\lorimer_ingest.py            # dry run
python D:\_PhotoAudit\scripts\lorimer_ingest.py --apply
```

Copy to local disk first — **never hash off the Drive mount**, it hangs with zero
bytes read rather than failing (learning 15). Re-running the ingest is safe: it is
content-hash deduped.

Afterwards `D:\_lorimer_stage` can go; its ingested files are hardlinks and the
library keeps the bytes.

### 2. Re-download Takeout 002, 003, 004

**To `C:`, never `D:`.** Three parallel downloads to `D:` made the partial files
*shrink* — 19.8 GB back to 18.5 GB — while writing at 0 MB/min. That is the drive
failing under sustained parallel write, the same signature as the retired E: drive.

**C: fits two at a time**, ~50 GB each against ~140 GB free. Start the driver first;
it watches `C:\Users\krish\Downloads` and `C:\GoogleTakeout`, consumes each archive
and deletes it, freeing room for the third.

```powershell
Start-Process python -ArgumentList "-u","D:\_PhotoAudit\scripts\driver.py" `
  -WindowStyle Hidden -RedirectStandardOutput "D:\_PhotoAudit\driver-run.log" `
  -RedirectStandardError "D:\_PhotoAudit\driver-err.log"
```

Launch detached — a tracked background task gets killed by the memory watchdog
(learning 9). After cancelling any long job, confirm the process actually died.

**New material lands in `Library\`, not `Personal\`.** Assign it a side afterwards
with `propose_split.py` and `apply_split.py`, and classify it with
`classify_screenshots.py`. Do not let a fresh ingest bypass the split.

### 3. Back up — the largest open risk

There is still no second copy. Capacity is **not** the constraint: `H:` is a 2 TB
account with ~1.65 TB free against a ~500 GB library. The mount *reports* ~133 GB
because `Get-PSDrive` returns the local cache volume (learning 17).

Back up **`PhotoLibrary\` and `ContentProduction\` and `Archive\`** — not the whole
drive, or the 320 GB of hardlinked bytes uploads twice.

**Batch it.** Drive for Desktop stages uploads through a cache on `C:`, so one giant
copy fills the system drive and dies partway. Check `C:` free space between batches.

The user's standing instruction was not to mirror before the audit. Raise it rather
than assume: the audit is now substantially done, and an unbacked library on a drive
throwing controller errors is the larger risk.

---

## Waiting on the user — do not act unprompted

- **`D:\PhotoLibrary\_Review\`** — 10,540 files (4.6 GB) classified as not-memories.
  Nothing was deleted. The user reviews and empties it.
- **`D:\Archive\99-Unsorted\`** — origins whose *side* is not established, plus
  messenger stickers. Keep it; it is the pressure valve that stops things being
  forced into a wrong category.
- **`Library\` (328 files)** — origins with no side assigned. Deliberately left in
  place rather than defaulted to Personal.

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
