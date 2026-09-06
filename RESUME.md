# RESUME PHOTOLIBRARY

**You have been asked to resume the media consolidation. Start here, then stop
reading and run the state check — every number below is a snapshot and may have
moved.**

```bash
cd C:\Users\krish\dev\contentarchives
git pull
python tools/refresh.py --check     # verify, write nothing
python tools/check_manifest.py      # every manifest row still points at a file
```

Then read, in order:

1. [`state/PROGRESS.md`](state/PROGRESS.md) — counted from disk, cannot have drifted
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the storage model and why the order matters
3. [`docs/LEARNINGS.md`](docs/LEARNINGS.md) — **read before changing any exclusion or deletion rule**
4. [`docs/HANDOVER.md`](docs/HANDOVER.md) — full detail on what has been consolidated

**Do not describe project state from memory or from this file's numbers.** That has
been wrong repeatedly. `track.py` counts files that exist.

---

## Where the work is paused

Everything is stopped. No robocopy, no python, no ffmpeg. Nothing is mid-write, so
nothing is in a state a reboot or a network change can corrupt.

**The reason it is paused:** the connection measured **1.5 Mbps** — the machine was
on a Wi-Fi extender (`_EXT` SSID), 2.4 GHz, 802.11n, while holding an unplugged
1 Gbps Ethernet port and a Wi-Fi 6 adapter. At that rate the remaining downloads
were a nine-day job. The user went to reconfigure the network.

**First thing to do on resume: re-measure the link.** Everything about sequencing
depends on it, and every earlier plan in this project that guessed at throughput was
wrong (learning 10).

```powershell
netsh wlan show interfaces | Select-String "SSID|Band|Radio type|Signal"
Get-NetAdapter | Select-Object Name, Status, LinkSpeed
$sw=[Diagnostics.Stopwatch]::StartNew()
$r=Invoke-WebRequest "https://speed.cloudflare.com/__down?bytes=10000000" -UseBasicParsing
$sw.Stop(); "{0:N2} MB/s" -f (($r.RawContentLength/1MB)/$sw.Elapsed.TotalSeconds)
```

---

## Open work, in priority order

**1. Finish the second machine's batch.** 781 of 1,525 files are staged locally at
`D:\_lorimer_stage` (2.39 GB of 6.96); 575 are already ingested. Resume the copy,
then re-run the ingest — it is content-hash deduped, so running it again over the
same folder cannot create duplicates.

```powershell
robocopy "G:\My Drive\_photo-consolidation\from-lorimer" "D:\_lorimer_stage" /E /R:2 /W:5 /NP /NFL /NDL /MT:8
python D:\_PhotoAudit\scripts\lorimer_ingest.py            # dry run first
python D:\_PhotoAudit\scripts\lorimer_ingest.py --apply
```

Copy from the Drive mount to local disk first — never hash directly off the mount
(learning 15).

**2. Re-download Takeout archives 002, 003, 004.** Cancelled; `D:\Takeout` is empty.
They go to **C:**, not D: — the partials on D: went *backwards* (19.8 → 18.5 GB)
while writing at 0 MB/min, which is the drive dropping under sustained write load,
the same signature as the failed E: enclosure.

**C: fits two at a time, not three** — ~50 GB each against ~140 GB free. The ingest
driver watches `C:\Users\krish\Downloads` and `C:\GoogleTakeout`, consumes each
archive and deletes it, freeing room for the third. Start it before downloading:

```powershell
Start-Process python -ArgumentList "-u","D:\_PhotoAudit\scripts\driver.py" `
  -WindowStyle Hidden -RedirectStandardOutput "D:\_PhotoAudit\driver-run.log" `
  -RedirectStandardError "D:\_PhotoAudit\driver-err.log"
```

Launch it detached like this — a tracked background task gets killed by the memory
watchdog (learning 9). After cancelling any long job, confirm the process actually
died; orphans have survived cancellation and competed for the same resource.

**3. Awaiting the user's decision — do not act unprompted.**

- **34 identity documents sit in the library** — passports, OCI cards, visas, birth
  certificates — swept in from `Downloads` and `Documents` folders. Listed in
  `D:\_PhotoAudit\SENSITIVE-FILES.csv`. Proposed: move to `D:\PersonalDocuments\`
  with the manifest following them. The user has been shown the list and has not
  yet decided.
- **`D:\_Staging\from-lorimer\`** holds 194 files in 6 origin folders whose category
  is genuinely ambiguous — a podcast recording and marketing video alongside an
  engagement lunch invitation. Grouped by origin folder so a person can settle it
  quickly. Do not guess these into `ContentProduction`.

**4. Deferred by the user, not forgotten.**

- `NoDate/` review — waits until the library is complete.
- Backup — **there is still no second copy of the library.** The largest open risk.
  The mirror to `H:` is deliberately gated on the audit (ARCHITECTURE.md), and the
  user has said explicitly not to mirror yet.

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

**The data-loss topic is closed.** 45 files were permanently lost early in this
project. The user has said to stop raising it unless files turn up in an archive.
The rules it produced still bind — see LEARNINGS.md 1 and 2 — but do not re-narrate
the incident or re-audit it.

---

## Standing constraints from the user

- **Progress lives in data, not in conversation.** Regenerate state; never assert it.
- Do not mirror to `H:` yet.
- Reviews and audits wait until the library is complete.
- Nothing built here should be throwaway — this toolkit gets reused on other
  machines, on old phone backups, and on digitising a family member's VHS tapes.

---

## Finishing a session

Commit state even if the work is half-done — **especially** then. A partial ingest
with an accurate checkpoint is recoverable; one with a stale record is not.

```bash
python tools/refresh.py
python tools/check_manifest.py
cd C:\Users\krish\dev\contentarchives
git add -A && git commit -m "Update state" && git push
```

If something was learned the hard way, add it to `LEARNINGS.md` with the incident
that produced it. The incident is the part that makes the rule stick.
