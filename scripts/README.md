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
| `apply_split.py` | apply an approved split, journalled, so a whole category can be moved back |
| `audit_deletions.py` | check every journalled deletion carries the evidence that justified it |
| `autopilot.py` | the ingest engine: streaming archive reader, dedupe, dating, placement |
| `big_files.py` | the largest files, surfaced for review rather than for action |
| `build_inventory.py` | rebuild the whole-library inventory from disk, one row per file that exists |
| `check_scratch_safe.py` | prove a scratch tree holds nothing unique - runs before clear_scratch |
| `check_tiny.py` | check what a size threshold would have discarded, before it does |
| `classify_screenshots.py` | separate screenshots from photographs without deleting either |
| `clear_scratch.py` | empty a scratch tree, but only after check_scratch_safe has passed |
| `diagnose_new.py` | ask why an ingest is calling everything new, against a baseline that excludes itself |
| `driver.py` | loops autopilot passes and survives the memory watchdog |
| `enrich_origin_status.py` | mark whether an origin still exists, and what deleting it would really free |
| `extract_zip_media.py` | stream out only the members not already held |
| `free_wins.py` | the reclaim that needs no judgement at all |
| `full_deletion_audit.py` | the exhaustive deletion audit, across every journal at once |
| `guarded_delete.py` | the only sanctioned delete: a proven surviving copy, or a named garbage category |
| `h_capacity.py` | size a cloud source set against local headroom before starting a pull |
| `ingest_eta.py` | projected finish time weighted by bytes, not by member count |
| `ingest_from_h.py` | stream a cloud mount into the library in batches, routed, deduped, resumable |
| `ingest_tree.py` | ingest any folder tree into the library, deduped and dated |
| `inspect_old_zips.py` | read export archives without extracting them |
| `lib_size_index.py` | size index of the library: the cheap first pass that rules out most dedup work |
| `machine_triage.py` | triage a machine's media by origin folder rather than extension |
| `migrate_layout.py` | restructure a library and rewrite every record in step, verified by count |
| `migrate_library.py` | move the library to a bigger drive and prove the copy by reading it back |
| `move_audio_to_h.py` | move files to a cloud mount, deleting only once the upload queue proves receipt |
| `move_to_review.py` | move a named set out of the chronology into review, never deleting |
| `paths.py` | every path in one place, so a rename is one edit and not eighty-five |
| `postswap_check.py` | after a drive-letter swap, prove the new disk really is the library |
| `propose_split.py` | propose a Personal/Communal split by origin folder, for review before anything moves |
| `purge_downgrades.py` | delete those worse copies, re-verified at the moment of deletion |
| `purge_redundant.py` | delete byte-identical copies, re-verified at the moment of deletion |
| `reclaim_d_originals.py` | find originals made redundant by a library copy - by inode, never by name |
| `reclaim_duplicates.py` | remove byte-identical duplicates, keeping the settled copy, verified at deletion |
| `reconcile_disk.py` | the disk is the truth; find what the records missed |
| `redate_videos.py` | re-date videos from the container clock instead of a folder name |
| `refresh_and_push.py` | regenerate the canon, verify it, push - refusing to push a false report |
| `restore_from_review.py` | put back files a rule evicted and a later judgement found were memories |
| `review_patterns.py` | characterise what a review bucket actually holds before acting on it |
| `runner.py` | run stages sequentially with measured, self-recalibrating ETAs |
| `space_audit.py` | where a volume's bytes actually are, counted by inode not by name |
| `space_tiers.py` | sort freeable bytes by how much judgement each tier needs |
| `store_summary.py` | summarise what the enrichment store actually holds |
| `survey_h_folders.py` | enumerate a cloud source set and report what the plan failed to name |
| `test_dedup.py` | tests for the dedup path |
| `to_content_production.py` | move produced content out of the chronology, manifest following |
| `triage_downgrades.py` | find re-encoded copies that are worse than what is already held |
| `validate_router.py` | test routing rules against known cases before trusting them on real files |
| `verify_dupes.py` | re-verify a duplicate claim by whole-file hash before anything acts on it |
| `verify_h_batch.py` | prove a pulled batch landed, by count and by hash |
| `verify_takeout_complete.py` | prove every archive member reached the library before deleting the archive |
| `video_variants.py` | find re-encodes and trims of the same footage - and refuse to touch chapters |
| `watch_d_downloads.py` | alarm on a partial download that shrinks or stalls |
| `whatsapp_breakdown.py` | characterise a messenger ingest before committing to it |
| `zip_fingerprint.py` | triage which export parts hold files the library lacks, from the central directory alone |
