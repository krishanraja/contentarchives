# 07 people

Ask a human what no model can know - who a face is - and record the answer so
nothing can ever overwrite it.

## Inputs
- face clusters and merges from 06 faces
- Krish's pasted answers; later, the game on a krishraja.com subdomain

## Outputs
- `D:\_enrichment\answers.csv`: the append-only journal, the only data in the
  project compute cannot reproduce
- `PEOPLE.html` naming sheets

## Invariants
- only people write the journal; no machine does, ever
- a row shown and not named is a REFUSAL and is recorded as such, so no face is
  ever offered twice: `record_people.py --sheet` writes `unidentifiable = declined`
  for every row on the sheet the paste does not name
- "?" and "for <who>" are questions, "unsure, blurry" is unidentifiable: none
  is ever recorded as a person
- a cluster id that does not exist is refused
- every crop on a sheet is checked against the assignment files before a human
  sees it
- every --apply refreshes the off-disk backup of the journal

## Code
| file | role |
|---|---|
| `stages/07_people/answers.py` | the append-only journal |
| `stages/07_people/swipe/server.py` | the swipe game prototype |
| `stages/07_people/people_sheet.py` | a page of faces to name, one row per person |
| `stages/07_people/verify_people_sheet.py` | every crop belongs to the row it is shown in |
| `stages/07_people/record_people.py` | record pasted answers into the journal, and back it up |

## Tests
- `tests/test_build_db.py`
- `tests/test_people_rounds.py`

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 48 | the page a human looks at is verified, not only the data behind it | `code:stages/07_people/verify_people_sheet.py:data-face` |
| 52 | a row shown and not named is recorded as declined, so no face is offered twice | `code:stages/07_people/record_people.py:shown and not named`, `test:tests/test_people_rounds.py:the BLANK row is recorded as declined` |
