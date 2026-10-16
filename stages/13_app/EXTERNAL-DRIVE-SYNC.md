# External drive sync: the prompt to run it

Run this whenever you want the external backup drive brought up to date. Nothing
depends on it: the app, its index and the nightly copy of the family's record
(in the cloud database and in the Drive folder "ContentArchives record") all run
in the cloud with the computer off. This only refreshes the drive's copy.

**How:** plug the backup drive in (any letter is fine), open PowerShell, go to
the folder where this repository is cloned, start Claude, and paste the prompt
below. It finds the drive, makes a safety copy, previews, runs the sync once,
checks the result and reports back. If one run stops at its 50 GB limit, paste
it again later and it carries on where it left off.

**One-time setup, already done on the library PC (2026-10-16):** the
environment variables `ARCHIVES_SUPABASE_URL` and
`ARCHIVES_SUPABASE_SERVICE_ROLE_KEY` set at User level. On a new PC, set them
first: copy the archives project's service_role key from the Supabase
dashboard, then in PowerShell run
`[Environment]::SetEnvironmentVariable('ARCHIVES_SUPABASE_URL', '<the project URL>', 'User')`,
and for the key, read it from the clipboard so it is never typed or shown:
`$v = (Get-Clipboard).Trim(); [Environment]::SetEnvironmentVariable('ARCHIVES_SUPABASE_SERVICE_ROLE_KEY', $v, 'User'); Remove-Variable v; Set-Clipboard -Value ' '`.
Then reopen PowerShell.

## The prompt

```text
Run the external drive sync for the family archive (repo krishanraja/contentarchives). Read AGENTS.md, NOW.md and stages\13_app\EXTERNAL-DRIVE-SYNC.md first. The cloud is the record and H: (Google Drive) holds the photographs; the external drive is only a backup, and this run only refreshes it.

RULES
- Never pass -Seed and never run seed_index.py --apply.
- Never print, log or paste the value of a secret. Report only "set" or "missing".
- Never edit code, never delete anything, never change a drive letter permanently.
- Don't commit or push.
- Stop and show me anything unexpected, word for word.

STEPS
1. Repo: in this clone, run `git status`. If the tree is not clean, stop and show me. Then run `git pull --ff-only origin main`.
2. Credentials: check that ARCHIVES_SUPABASE_URL and ARCHIVES_SUPABASE_SERVICE_ROLE_KEY are set in this process (set/missing only). If either is missing, read it from the User scope with [Environment]::GetEnvironmentVariable(<name>, 'User'), without printing it. Confirm Python will use them:
   python -c "import stagepath, cloud; u,k,n=cloud.credentials(); print(n, 'url set' if u else 'url MISSING', 'key set' if k else 'key MISSING')"
   It must name the ARCHIVES_ pair. If not, stop.
3. The drive: find the backup drive. It's the drive (any letter) holding both _PhotoAudit\library.db and _enrichment\answers.csv.
   - None found: tell me it isn't plugged in and stop.
   - If <drive>\_PhotoAudit\APP-SYNC-HALTED.txt exists, show me its contents and stop.
4. Safety copy: make <drive>\_PhotoAudit\pre-sync-<yyyyMMdd-HHmm> and copy these into it, confirming each by SHA-256:
   - <drive>\_enrichment\answers.csv
   - <drive>\_enrichment\game-ingest-cursor.json (if present)
   - <drive>\_PhotoAudit\library.db
   Record the line count of answers.csv and the last-write time of library.db.
5. Preview, which writes nothing: python -u stages\13_app\backup_to_drive.py --drive <drive>:\
   Report the cloud record's day and row counts, and how many photographs it would copy and their size.
6. Run the sync once. I approve this one run, without -Seed: pwsh -NoProfile -File stages\13_app\chain_app_sync.ps1
   (If pwsh is missing, use powershell.exe -NoProfile -ExecutionPolicy Bypass -File ... instead.) It maps the drive to D: for the run if it has another letter, and unmaps it at the end. The rebuild can take a while; watch D:\_PhotoAudit\app-sync.log and don't start a second run.
7. Verify, and give me numbers rather than a summary:
   a. this run's log section ends with "[seed] skipped" then "APP SYNC COMPLETE", with no "[merge] exited" line;
   b. the "cloud rows marked" line;
   c. the "[backup]" section: record saved under _cloud-record\<day>; photographs copied, GB, already there, missing on H:. "Stopped at --max-gb" is fine: run this prompt again later to continue;
   d. answers.csv's line count and library.db's last-write time, against step 4;
   e. the cloud count of status=new answers older than 15 minutes (expect 0), using stages\13_app\cloud.py read-only;
   f. D: is unmapped afterwards (if it was mapped) and there is no halt file.

REPORT BACK
- What was verified, with the numbers from step 7, and what was not.
- Any warning, refusal or STOPPED line, word for word.
- Leave the safety copy from step 4 in place.
```
