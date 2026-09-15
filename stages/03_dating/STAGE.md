# 03 dating

Work out when each photograph or video was actually taken, from evidence the
camera wrote, and say "no date" rather than invent one.

## Inputs
- a file, its filename, its EXIF, its container metadata, any sidecar JSON

## Outputs
- a date and the source it came from, or `NoDate\`

## Invariants
- precedence: filename, EXIF, container clock, sidecar, folder name, give up
- modification times are never a date
- implausible years and known-bogus epochs are rejected

## Code
| file | role |
|---|---|
| `contentarchives/dating.py` | the date precedence chain, the reusable core |
| `scripts/redate_videos.py` | re-date videos from the container's own clock |

## Tests
- none yet: dating has no test file (debt)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 3 | mtime is never a date | `code:contentarchives/dating.py:def date_for` |
| 19 | a video's container clock outranks the folder it arrived in | `code:scripts/redate_videos.py:creation_time` |
