# The catalogue: everything known about every photograph, on both copies

`export_record.py` writes it every night into `record_exports` (migration 0017),
and `backup_to_drive.py` copies the newest night to the backup drive as
`<drive>\_cloud-record\<day>\catalogue.csv.gz`. One row per photograph or video
the app's index holds, ordered by `hash`.

Why it exists. Krish, 2026-10-16, asked whether the cloud should move files into
year folders when the family dates them: "No, the app organizes. But set this up
so that in the future, I can use the enriched information to resegment in both
the external drive and the H drive." Nothing moves files today. This file is the
input a future re-sort reads: for each photograph it says where it is on each
copy, and what date, place and people it has, and how far to trust each.

## Finding the file on each copy

| column | meaning |
|---|---|
| `hash` | the index's key: the library's blake2b, or `drive:<id>` for a file that reached Drive without passing through the library |
| `md5` | the file's md5. Drive reports it, so it identifies the file on the backup drive too (the mirror journal `h-mirror.csv` and `backup-from-h.csv` record md5 against path). Empty for the few the library knew no md5 for |
| `drive_id` | the Drive file id on H:. Empty when the file has left Drive (the index keeps what it knew) |
| `rel_path` | the path under `ContentLibrary`, `/`-separated, on H: (`H:\My Drive\ContentLibrary\...`) and, for files the backup drive received from H:, on the backup drive (`<drive>\ContentLibrary\...`) |
| `side` | `Communal` or `Personal`, from the path |
| `media` | `photo` or `video` |
| `visible`, `hidden`, `hidden_by` | whether the app shows it, and if hidden, what hid it (`rule:private`, `rule:video-check`, a person). A re-sort must keep a hidden file hidden |

## When it was taken

| column | meaning |
|---|---|
| `best_when` | the date the app shows: the family's answer, else the camera's clock (`YYYY-MM-DD`), else the year folder, else the library's estimate. The same order as `web/lib/when.ts` |
| `when_source` | `family`, `camera`, `folder`, `library`, or empty. A re-sort into year folders can choose which sources it trusts |
| `when_year` | a year from `best_when` where one can be read (the first year of a decade) |
| `family_when`, `taken_at`, `year`, `approx_year` | the separate inputs, so nothing is lost by `best_when` choosing |

## Where it was taken

| column | meaning |
|---|---|
| `best_place` | the place the app shows: the family's answer, else the index's |
| `place_source` | `family`, `index`, or empty |
| `family_place`, `place`, `region`, `country`, `lat`, `lon` | the separate inputs |

## Who and what

| column | meaning |
|---|---|
| `people` | everyone in it, `; `-separated, as the app counts them: face groups the family named, plus each relative's latest yes or no on who is in it (migration 0012). Derived names (`cluster-merge`) on the PC library are not in the cloud and are not here |
| `day_key` | photographs from one run of time ("the same day" in the app) |
| `description`, `objects`, `activity`, `occasion`, `mood` | the index's description of the picture |
| `width`, `height`, `source`, `updated_at` | as the index holds them |

## Not in it

- Files the cloud **held** and never showed (`held`): the sensitivity rule keeps
  them out of the index, so a re-sort meets them as files the catalogue does not
  name. Leave those where they are.
- Anything outside `Media\Communal` and `Media\Personal`.

## The other two files

`answers.csv.gz` is every row of `answers` (what the family said in the app,
with its status), and `journal.csv.gz` is the library's journal imported once.
Together they are the family's record; the catalogue is what they add up to.
