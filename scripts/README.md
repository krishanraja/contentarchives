# Working scripts

The scripts that actually ran the consolidation, kept here so they
are not lost with the machine they ran on.

**These are working scripts, not a library.** Paths are hardcoded
to the machine they were written for, and names have been redacted
for publication, so they will not run unmodified. The tested,
generalised versions of the safety, dating and dedupe logic live in
`contentarchives/`; these show how the whole job was actually done.

| script | purpose |
|---|---|
| `already_in_library.py` | find files whose content is already safely in the library |
| `autopilot.py` | the ingest engine: streaming archive reader, dedupe, dating, placement |
| `check_tiny.py` | check what a size threshold would have discarded, before it does |
| `driver.py` | loops autopilot passes and survives the memory watchdog |
| `extract_zip_media.py` | stream out only the members not already held |
| `ingest_tree.py` | ingest any folder tree into the library, deduped and dated |
| `inspect_old_zips.py` | read export archives without extracting them |
| `machine_triage.py` | triage a machine's media by origin folder rather than extension |
| `purge_redundant.py` | delete byte-identical copies, re-verified at the moment of deletion |
| `redate_videos.py` | re-date videos from the container clock instead of a folder name |
| `refresh_and_push.py` | regenerate the canon, verify it, push - refusing to push a false report |
| `runner.py` | run stages sequentially with measured, self-recalibrating ETAs |
| `space_audit.py` | where a volume's bytes actually are, counted by inode not by name |
| `space_tiers.py` | sort freeable bytes by how much judgement each tier needs |
| `to_content_production.py` | move produced content out of the chronology, manifest following |
| `whatsapp_breakdown.py` | characterise a messenger ingest before committing to it |
| `zip_fingerprint.py` | triage which export parts hold files the library lacks, from the central directory alone |
