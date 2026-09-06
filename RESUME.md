# RESUME PHOTOLIBRARY

**You have been asked to resume the media consolidation. Start here, then stop
reading and run the state check — every number below is a snapshot and may have
moved.**

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

Then read, in order:

1. [`state/PROGRESS.md`](state/PROGRESS.md) — counted from disk, cannot have drifted
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the storage model and why the order matters
3. [`docs/LEARNINGS.md`](docs/LEARNINGS.md) — **read before changing any exclusion or deletion rule**
4. [`docs/HANDOVER.md`](docs/HANDOVER.md) — full detail on what has been consolidated

**Do not describe project state from memory or from this file's numbers.** That has
been wrong repeatedly. `track.py` counts files that exist.

---

# THE PLAN — start here

Work is split by what it needs. The network was measured at **1.5 Mbps** on a 2.4 GHz
Wi-Fi extender with the Ethernet port unplugged; an upgrade to 5 GHz and wired was
planned for **2026-09-07**. Everything bandwidth-bound was deferred to that.

## FIRST, ALWAYS: measure the link

Every plan below depends on it, and every throughput guess made on this project
before measuring has been wrong (learning 10, learning 15).

```powershell
netsh wlan show interfaces | Select-String "SSID|Band|Radio type|Signal"
Get-NetAdapter | Select-Object Name, Status, LinkSpeed
$sw=[Diagnostics.Stopwatch]::StartNew()
$r=Invoke-WebRequest "https://speed.cloudflare.com/__down?bytes=10000000" -UseBasicParsing
$sw.Stop(); "{0:N2} MB/s" -f (($r.RawContentLength/1MB)/$sw.Elapsed.TotalSeconds)
```

Report the figure before starting. If it is still ~1.5 Mbps the network change did
not take, and none of the tasks below are worth beginning.

---

## TOMORROW — needs the fast connection

### 1. Finish the second machine's batch

744 of 1,525 files are still only on the Drive mount. 781 are staged at
`D:\_lorimer_stage`; 698 are ingested.

```powershell
robocopy "G:\My Drive\_photo-consolidation\from-lorimer" "D:\_lorimer_stage" /E /R:2 /W:5 /NP /NFL /NDL /MT:8
python D:\_PhotoAudit\scripts\lorimer_ingest.py            # dry run
python D:\_PhotoAudit\scripts\lorimer_ingest.py --apply
```

Copy to local disk first — **never hash directly off the Drive mount**, it hangs
with zero bytes read rather than failing (learning 15). Re-running the ingest is
safe: it is content-hash deduped, so it cannot place anything twice.

### 2. Re-download Google Takeout 002, 003, 004

**To `C:`, never `D:`.** Downloading three in parallel to `D:` made the partial files
*shrink* — 19.8 GB back to 18.5 GB — while writing at 0 MB/min. That is the drive
failing under sustained parallel write, the same signature as the retired E:
enclosure.

**C: fits two at a time**, not three: ~50 GB each against ~140 GB free. Start the
ingest driver first — it watches `C:\Users\krish\Downloads` and `C:\GoogleTakeout`,
consumes each archive and deletes it, freeing room for the third.

```powershell
Start-Process python -ArgumentList "-u","D:\_PhotoAudit\scripts\driver.py" `
  -WindowStyle Hidden -RedirectStandardOutput "D:\_PhotoAudit\driver-run.log" `
  -RedirectStandardError "D:\_PhotoAudit\driver-err.log"
```

Launch detached like that — a tracked background task gets killed by the memory
watchdog (learning 9). After cancelling any long job, confirm the process actually
died; orphans have survived cancellation here and competed for the same resource.

### 3. Back up the library — the largest open risk

There is still no second copy. Capacity is **not** the constraint: `H:` is a 2 TB
account with roughly **1.65 TB free** against a ~520 GB library. The mount *reports*
about 133 GB because `Get-PSDrive` returns the local cache volume's free space
(learning 17) — do not plan from that number.

Back up **`PhotoLibrary/` and `ContentProduction/` only.** Backing up more re-uploads
the 320 GB of hardlinked bytes a second time.

**Batch it.** Drive for Desktop stages uploads through a local cache on `C:`, so one
giant copy fills the system drive and dies partway. Copy in batches, checking `C:`
free space between them.

The user's standing instruction was not to mirror before the audit. Raise it rather
than assume: the audit is now far enough along that an unbacked library on a drive
throwing controller errors is the bigger risk.

---

## AFTER THE ABOVE — no longer bandwidth-bound

- **`NoDate/` review.** Deferred by the user until the library is complete.
- **Quarantine batches.** Separating personal from communal family content, chosen by
  origin folder using `state/origin-folders.csv`. This is what the origin map was
  built for.
- **34 identity documents** still in the library — passports, OCI cards, visas, birth
  certificates, listed in `D:\_PhotoAudit\SENSITIVE-FILES.csv`. Proposed move to
  `D:\PersonalDocuments\` with the manifest following. The user has seen the list and
  not yet decided. **Do not act unprompted.**
- **`D:\_Staging\from-lorimer\`** — 194+ files in origin folders whose category is
  genuinely ambiguous: a podcast recording and marketing video alongside an engagement
  lunch invitation. Grouped so a person can settle it in a minute. **Do not guess
  these into `ContentProduction`.**

---

## Decisions already made — do not reopen these

| Decision | Why |
|---|---|
| `H:` stages oversized and cross-machine files; becomes D:'s mirror **only after** the audit | mirroring an unaudited library propagates its mistakes |
| `D:` is the single local endpoint everything converges on | |
| Repo is public; folder-level origin map published, per-file map stays local | the per-file map leaks through filenames — passport and visa scans name themselves |
| Compression **abandoned** | measured, not assumed: grainy footage has a quality ceiling, and 4K HEVC ran at 0.1× realtime |
| Produced content lives in `ContentProduction/`, outside the library ontology | |
| The second machine's software screenshots are held in `_Staging`, not ingested | 1,055 QA shots would make the personal/communal split harder |
| Large videos are all kept | precious memories and travel footage |
| Downloads go to `C:`, never `D:` | D: corrupts partial files under parallel write load |

**The data-loss topic is closed.** 45 files were permanently lost early in this
project. The user has said to stop raising it unless files turn up in an archive. The
rules it produced still bind — LEARNINGS 1 and 2 — but do not re-narrate the incident.

---

## Standing constraints from the user

- **Progress lives in data, not in conversation.** Regenerate state; never assert it.
- Reviews and audits wait until the library is complete.
- Nothing built here should be throwaway — this toolkit gets reused on other machines,
  on old phone backups, and on digitising a family member's VHS tapes.
- One thing at a time when bandwidth or the disk is the constraint.

---

## Finishing a session

Commit state even if the work is half-done — **especially** then. A partial ingest
with an accurate checkpoint is recoverable; one with a stale record is not.

```bash
python tools/refresh.py
python tools/check_manifest.py
git add -A && git commit -m "Update state" && git push
```

If something was learned the hard way, add it to `LEARNINGS.md` with the incident that
produced it. The incident is the part that makes the rule stick.
