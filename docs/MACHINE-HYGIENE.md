# Machine hygiene runbook — bring a Windows machine to the same clean state

**Audience.** A Claude Code (or Codex / Cursor) session on Krish's *other* Windows
machine, tasked with reproducing the 2026-09-07 cleanup so both machines are in the
same state.

**What this achieves.** OneDrive permanently decommissioned, reclaimable caches
cleared, the Windows profile root de-sprawled, and *enforcement* so it does not come
back. On the reference machine this reclaimed **185 GB** and took the profile root
from 68 stray directories + 109 loose files down to zero.

> **Read the "Gotchas" section at the end BEFORE you start.** Several steps look
> obvious and are wrong in ways that silently destroy work or silently do nothing.
> Every one of them was hit for real on the reference machine.

Throughout, `<PROFILE>` means the Windows profile root (`C:\Users\<you>`). Do not
assume the username matches the reference machine — resolve it from `$env:USERPROFILE`.

---

## Phase 0 — Ground yourself first

1. Read the file-routing card (`~/.claude/runbooks/file-routing.md`) and the OS
   architecture doc it points at. **Do not invent destinations.** The routing rules
   below are a summary, not the authority.
2. Establish current truth — never trust a memory file's claim that something was
   already disabled. On the reference machine a "disabled" service had silently
   re-enabled itself.

```powershell
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
  Select DeviceID,@{n='FreeGB';e={[math]::Round($_.FreeSpace/1GB,1)}},@{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}}
Get-PhysicalDisk | Select FriendlyName,MediaType,HealthStatus,OperationalStatus
Get-Process | Sort CPU -Descending | Select -First 10 ProcessName,CPU,@{n='MB';e={[math]::Round($_.WS/1MB)}}
```

Divide each process's CPU seconds by uptime seconds. Anything above ~100% of one core
sustained is your real performance problem — find it before optimising anything else.

---

## Phase 1 — OneDrive decommission

**Only if the same decision applies on this machine.** On the reference machine Krish
will not use OneDrive again; it exists as cloud storage (web) only.

### ⚠️ Read this before touching OneDrive

If large numbers of files were previously deleted locally while sync was off, those
deletions have **never been replayed to the cloud**. Re-enabling sync can propagate
them to the live account. **If OneDrive is ever wanted again: UNLINK AND RESET FIRST.**
Never simply flip the policy back.

### Steps, in this order

The order matters. Apply the policy *before* killing the processes, or OneDrive
respawns and re-registers itself mid-operation.

```powershell
# 1. Policy kill switch FIRST - this is what actually holds
$p = 'HKLM:\SOFTWARE\Policies\Microsoft\OneDrive'
New-Item $p -Force | Out-Null
Set-ItemProperty $p -Name DisableFileSyncNGSC -Value 1 -Type DWord
Set-ItemProperty $p -Name DisableFileSync     -Value 1 -Type DWord
$p6 = 'HKLM:\SOFTWARE\WOW6432Node\Policies\Microsoft\OneDrive'
New-Item $p6 -Force | Out-Null
Set-ItemProperty $p6 -Name DisableFileSyncNGSC -Value 1 -Type DWord

# 2. Then stop it
& "$env:ProgramFiles\Microsoft OneDrive\OneDrive.exe" /shutdown; Start-Sleep 5
Get-Process OneDrive,OneDrive.Sync.Service,FileCoAuth -EA 0 | Stop-Process -Force

# 3. Autostart off (both the Run keys AND OneDrive's own flag)
$run = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
(Get-Item $run).GetValueNames() | ForEach-Object { "$_ = $((Get-Item $run).GetValue($_))" } |
  Set-Content "$env:USERPROFILE\.scratch\autostart-backup.txt"     # back up first
foreach ($n in 'OneDrive','Microsoft.Lists') {
  if ((Get-Item $run).GetValue($n)) { Remove-ItemProperty $run -Name $n -Force }
}
Set-ItemProperty 'HKCU:\SOFTWARE\Microsoft\OneDrive' -Name AutoStartEnabled -Value 0 -Type DWord
```

### Undo Known Folder Move

Check where the user folders actually point (read *unexpanded*, or you cannot tell a
redirect from a literal path):

```powershell
$k = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
foreach ($n in 'Desktop','Personal','My Pictures','My Music','My Video',
               '{374DE290-123F-4565-9164-39C4925E467B}') {
  '{0,-42} = {1}' -f $n, (Get-Item $k).GetValue($n,'','DoNotExpandEnvironmentNames')
}
```

For each folder still pointing into OneDrive:

1. **Check for cloud-only placeholders first** — attribute `0x400000`
   (`RECALL_ON_DATA_ACCESS`). With sync disabled they cannot hydrate; moving them
   creates dead stubs. Decide explicitly with Krish: leave, fetch from the web, or delete.
2. Confirm the local counterpart does **not** already exist, or you are merging two
   trees rather than moving one. Abort if it exists.
3. `Move-Item` the folder out, then repoint **both** registry keys:
   `User Shell Folders` (as `ExpandString`, e.g. `%USERPROFILE%\Desktop`) **and** the
   legacy `Shell Folders` (as `String`, fully expanded).
4. `Stop-Process -Name explorer -Force` — the change is invisible to running apps until
   Explorer restarts.

Verify all six user folders now resolve locally before moving on.

---

## Phase 2 — Reclaim space

Measure before deleting. On the reference machine the space was **not** where anyone
expected. Check these in order:

| Location | What it is | Safe to clear? |
|---|---|---|
| `~\.codex\sessions\*.jsonl` | Codex session transcripts | **Yes, older than ~7 days.** Nothing prunes these. A single runaway session wrote ~20 files at **2 GB each**. Cost: `codex resume` on old sessions stops working. |
| `%LOCALAPPDATA%\Google\DriveFS\<acct>\content_cache` | Drive file cache | **Yes.** Independent of the metadata sqlite DBs beside it, so the index survives and only content re-downloads. Quit Drive first. |
| `%LOCALAPPDATA%\CoreAIPlatform.00` | **Windows Recall** screenshot store | Yes — see below. Check whether Recall is capturing at all. |
| `%LOCALAPPDATA%\npm-cache`, `~\.cache`, `ms-playwright`, `pnpm-cache`, `pip\Cache` | Rebuildable dev caches | Yes. Cost: slower next install. |
| `%TEMP%`, `C:\Windows\Temp`, `SquirrelTemp`, `CrashDumps`, `*-updater` | Pure garbage | Yes. |
| `C:\` stray dirs | Installer/PUP leftovers | Inspect first; some are bundled-adware residue. |

Google Drive must be stopped before clearing its cache, and it unmounts its drive
letters when it quits — expect them to disappear and come back:

```powershell
$exe = (Get-Process GoogleDriveFS -EA 0 | Select -First 1).Path
Start-Process $exe -ArgumentList '--quit'; Start-Sleep 12
# clear only  <acct>\content_cache  - never the sibling metadata_sqlite_db files
Start-Process $exe            # relaunch, then confirm the drive letters return
```

Windows Recall, if you want it gone rather than merely emptied:

```powershell
$w = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsAI'
New-Item $w -Force | Out-Null
Set-ItemProperty $w -Name DisableAIDataAnalysis -Value 1 -Type DWord
Disable-WindowsOptionalFeature -Online -FeatureName Recall -NoRestart
```

> This sets a **pending reboot**, which then blocks DISM component-store repair until
> you restart. See Phase 5.

---

## Phase 3 — De-sprawl the profile root

### The rule

Nothing lives loose in `<PROFILE>`. First match wins:

1. Code / repo / build artifact → `<PROFILE>\dev\<venture>\<repo>\` (venture = git **remote identity**, not folder name)
2. AI-training corpus → `<PROFILE>\dev\<venture>\_corpus\`
3. Personal (wealth / legal / family / media) → `G:\My Drive\Personal\...`
4. Scratch / QA output / screenshots / temp / one-off audits → `<PROFILE>\.scratch\`
5. Cross-venture timeless IP → `G:\My Drive\Ventures\_Knowledge\<sub>\`
6. Single-venture deliverable → `G:\My Drive\Ventures\Active\<Venture>\0X_*\`
7. Unsure → **ask**; never dump at root.

Legitimately at the root: dotfiles and dot-directories, `AppData`, the standard user
folders, the `NTUSER.*` hives, junctions, and `dev\`.

### ⚠️ Audit every repo before deleting anything

This is the step that destroys work if rushed. "It's an old clone, bin it" is wrong
often enough to matter. On the reference machine a blanket delete would have lost 11
unpushed commits, an ungitted research corpus, and two repos with **no remote at all**.

For each candidate:

```bash
git -C "$d" log --branches --not --remotes --oneline   # unpushed on ANY branch
git -C "$d" stash list                                  # stashes
git -C "$d" remote get-url origin                       # NO REMOTE = nothing is backed up
git -C "$d" status --porcelain                          # uncommitted work
```

- Checking only the current branch's ahead-count is **not sufficient** — it misses
  every other local branch.
- A repo with **no origin** must never be deleted casually. Nothing about it exists
  anywhere else.
- Before deleting, sweep untracked non-junk files somewhere safe
  (`git ls-files --others --exclude-standard`), skipping `node_modules/`, `dist/`,
  `test-results/`. A research corpus lived only as an untracked `.docx`.
- Salvage any stray credential files you find into a quarantine folder and tell Krish
  to file them properly. Do not leave them in a repo and do not paste them anywhere.

### Pruning stale branches

`git branch --merged` misses squash-merged branches. Two reliable signals:

- `git branch -vv` showing `[origin/<name>: gone]` — the remote branch was deleted,
  which in this workflow means the PR merged.
- **Authoritative:** ask GitHub. `gh pr list --head <branch> --state all --json number,state,mergedAt`

Do **not** verify by grepping commit messages. `git log --grep` searches commit
*bodies* too and squash merges reword subjects, so it produces confident false matches
in both directions. On the reference machine that method wrongly reported four branches
as merged when their PRs were actually **closed** (their content had landed via
different PRs — which only the content check revealed).

---

## Phase 4 — Prevention (the part that makes it stick)

A rule written in a card is advice. On the reference machine the card already said
"never write loose files into the profile root" and 109 files accumulated anyway.
Four layers, weakest to strongest:

### 4a. Claude Code guard hook (hard enforcement)

Copy `tools/machine-hygiene/guard-profile-root.mjs` from this repo into
`~/.claude/hooks/` and register it in `~/.claude/settings.json` under
`PreToolUse` for **both** `Bash` and `Write|Edit|NotebookEdit`. **Merge with existing
hooks; do not replace the array.**

```json
{ "type": "command",
  "command": "node C:/Users/<you>/.claude/hooks/guard-profile-root.mjs" }
```

**Use forward slashes.** See Gotcha 1 — this is not cosmetic.

It blocks: `Write` to the root; `git clone` / `touch` / `mkdir` / `cp` / `mv` /
redirections targeting the root; and any file-producing command whose **cwd is the
root**. It allows: dotfiles, standard user folders, editing files already at the root,
read-only commands at the root, and root paths appearing inside heredoc bodies (data,
not writes).

Verify with a test suite before trusting it, and then verify it actually *fires* —
those are different things (Gotchas 1 and 2).

### 4b. Codex

Codex has no user-definable tool-interception hook. Two things you *can* do:

- Remove the profile root from `~/.codex/config.toml` if present as a trusted project.
  `[projects.'c:\users\<you>'] trust_level = "trusted"` actively invites Codex to work
  there. Also prune entries pointing at decommissioned paths (e.g. OneDrive).
  **Back up `config.toml` first.**
- Update `~/.codex/AGENTS.md` and `<PROFILE>\AGENTS.md` (keep them identical) with the
  routing rule *and* an explicit "never operate from the profile root" instruction.
  Check the venture list is current — the reference machine's copy still named two
  ventures retired months earlier.

### 4c. Cursor

Create `~/.cursor/rules/file-routing.mdc` with `alwaysApply: true`. Cursor also reads
`AGENTS.md`, so 4b covers it partially.

### 4d. Janitor sweep (the real backstop)

The guard hook only sees Claude Code's own tool calls. Nothing stops Codex, Cursor, an
installer, or a stray script. Copy `tools/machine-hygiene/sweep-profile-root.mjs`
from this repo into `~/.claude/hooks/`
(report-only by default; `--apply` quarantines into `.scratch\root-strays\<date>\`,
moving and never deleting) and schedule it:

```powershell
$a = New-ScheduledTaskAction -Execute "$env:ProgramFiles\nodejs\node.exe" `
     -Argument "$env:USERPROFILE\.claude\hooks\sweep-profile-root.mjs --apply"
Register-ScheduledTask -TaskName 'ProfileRootJanitor' -Action $a `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 9am) `
  -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force
```

Run the exact command by hand once to confirm the node path resolves.

---

## Phase 5 — Confirm health

```powershell
Get-PhysicalDisk | Select FriendlyName,HealthStatus,OperationalStatus
Get-Volume -DriveLetter C | Select HealthStatus
(Get-MpComputerStatus) | Select RealTimeProtectionEnabled,AntivirusSignatureAge
Get-MpThreat | Where IsActive                       # expect nothing
(Repair-WindowsImage -Online -CheckHealth).ImageHealthState
Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'
```

Interpreting the results:

- **`ImageHealthState = Repairable`** → run `Repair-WindowsImage -Online -RestoreHealth`.
  If it stays `Repairable`, check for a pending reboot — **CBS refuses to finish
  servicing while `C:\Windows\WinSxS\pending.xml` exists**, so the repair cannot
  complete. Reboot, then re-check, then repair again if needed. Removing an optional
  feature (e.g. Recall) creates exactly this state.
- **Cumulative CPU is misleading.** Sample twice ~20s apart and difference it; a
  process that merely *accumulated* CPU during your file moves is not a live problem.
  Judge total load across all cores, not one process's counter.
- A remediated historical Defender detection is not a current problem. Check
  `IsActive`, and confirm the flagged file is actually gone.

---

## Gotchas — each of these cost real time

1. **Hook commands run through Git Bash, where `\` is an escape character.**
   `node C:\Users\me\.claude\hooks\x.mjs` becomes `node C:Usersme.claudehooksx.mjs`,
   node fails with "Cannot find module", and the hook **fails silently on every
   invocation**. Use forward slashes. On the reference machine an unrelated hook had
   been dead this way for three months and nobody noticed. Audit existing hooks for it.

2. **A hook that validates is not a hook that runs.** Valid JSON, a passing test suite
   and a correct matcher prove nothing about whether it fires. Prove it end-to-end:
   attempt the thing it should block, or have it append to a sentinel file and check.
   Config changes may also need the settings watcher to reload.

3. **OneDrive re-enables its own autostart.** Removing the `Run` key is not enough — it
   recreates it (plus a second `Microsoft.Lists` entry) and refreshes
   `AutoStartEnabled`. Only the Group Policy kill switch holds.

4. **Cumulative CPU ≠ current CPU.** See Phase 5.

5. **`git log --grep` searches commit bodies and squash merges reword subjects.** Never
   confirm "this branch was merged" that way. Ask GitHub.

6. **Only the current branch's ahead-count is not an audit.** Use
   `--branches --not --remotes` plus `git stash list`, and treat a missing `origin` as
   a hard stop.

7. **Purging a cache directory can break tooling that points into it.** On the
   reference machine clearing `~/.cache` deleted a plugin marketplace directory
   referenced by `settings.json`; it kept working until the next restart. Grep your
   config files for any path you are about to delete.

8. **Deleting `%TEMP%` can delete your own session's working files.** Exclude the
   harness scratch directory, or expect to lose the output of the command doing the
   deleting.

9. **Cloud-only placeholders cannot hydrate once sync is disabled.** Decide what
   happens to them *before* you disable sync, not after.

10. **A one-line local dev tweak can look like uncommitted work.** On the reference
    machine an `allowedHosts` line in `vite.config.ts` was modified in nearly every
    repo. Read the diff before treating dirt as valuable.

---

## Reference outcome (2026-09-07)

| | Before | After |
|---|---|---|
| C: free | 467.8 GB | 653 GB (**+185 GB**) |
| Profile root | 68 stray dirs, 109 loose files | 0 |
| OneDrive | ~2.2 cores pegged, self-re-enabling | policy-disabled, all folders local |
| Boot autostart | 8 entries | 2 |
| Enforcement | a card nothing read | guard hook + Codex/Cursor rules + daily janitor |

Remaining on the reference machine at time of writing: one reboot to clear the pending
CBS operation and finish the component-store repair.
