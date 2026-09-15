# 01 sources

Find out what a drive, machine or export actually holds, before anything is
copied: names, sizes and completeness, read cheaply and never trusted blindly.

## Inputs
- a source: an external drive, a second machine, a cloud mount, a Takeout export

## Outputs
- a survey of the source and what the plan did not name
- a decision about which parts are worth ingesting

## Invariants
- the set is enumerated independently of the plan, and the difference is printed
- a cloud mount is read by copying locally first; a hang is measured, not waited on
- an export part is judged by its contents, never its number

## Code
| file | role |
|---|---|
| `scripts/survey_h_folders.py` | read the names on a source and report what the plan missed |
| `scripts/h_capacity.py` | size a source against local headroom before pulling |
| `scripts/inspect_old_zips.py` | read export archives without extracting them |
| `scripts/zip_fingerprint.py` | which export parts hold files the library lacks |
| `scripts/verify_takeout_complete.py` | prove every archive member reached the library |
| `scripts/machine_triage.py` | triage a machine's media by origin folder |
| `scripts/watch_d_downloads.py` | alarm on a download that shrinks or stalls |
| `scripts/whatsapp_breakdown.py` | characterise a messenger ingest before committing |
| `scripts/video_variants.py` | find the same footage twice before ingesting it |

## Tests
- none yet: every lesson below is enforced by code, not by a test (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 12 | a drive that drops under write load is watched, not trusted | `code:scripts/watch_d_downloads.py:stall` |
| 14 | triage by origin folder, not extension | `code:scripts/machine_triage.py:origin` |
| 15 | measure a hung mount's I/O before calling it slow | `code:scripts/h_capacity.py:learning 15` |
| 24 | a skip needs the same proof as a delete when the source is going away | prose-only |
| 26 | export parts judged by their central directory | `code:scripts/zip_fingerprint.py:central`, `code:scripts/verify_takeout_complete.py:member` |
| 33 | enumerate the source independently of the plan | prose-only |
