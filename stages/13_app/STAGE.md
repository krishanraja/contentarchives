# 13 app

The family app at archives.krishraja.com: Communal photographs searchable on a
phone, and the questions only family can answer - who is this, where was it,
roughly when - asked of grandparents one at a time and written back to the
journal under their own names. Krish, 2026-10-04: it reads from Google Drive,
"always on and accessible, no reliance on a local drive"; it is built for older
people ("make it idiotproof"); and "it is imperative there is no sensitive
nudity in this".

## Inputs
- **Google Drive's Communal folder, through the read-only service account: the
  only input the app needs.** Krish, 2026-10-04: "Nothing about the D drive exists
  for this session" - no step may depend on D: or any PC.
- optional, only when D: is connected (the bridge): `library.db` (08 index), the
  share rules' raw sensitivity tags, `PURGED-HASHES.csv`
- face groups and assignments (06 faces), the answers journal and Bharti's queue (07 people)
- `desc-vectors` and `EVENTS.json` (08 index), `h-mirror.csv` (11 mirror) for Drive md5s
- `app.players` in the profile (outside the repo)
- Google Drive's Communal folder, read by the app's service account (Viewer on that folder only)

## Outputs
- the cloud index (Supabase): photos, faces, clusters, groups, queue, people -
  DERIVED, written by ONE writer, `cloud_enrich.py`, on GitHub Actions daily
- the app's `answers` table: what the family said, the system of record until pulled
- answers.csv rows under each relative's name, via `ingest_game_answers.py`
- `D:\_PhotoAudit\app-seed\` (the bundle, holds family names: never published)

## Invariants
- one writer builds the index: `cloud_enrich.py`, from Drive alone; the web app
  only reads it (and records answers); its Drive route is a read-only health check
- its public log carries numbers only - never a path, a name or a description
- a cluster id is never reissued: the next id clears every id already in the table
- a name belongs to the CLUSTER the person was shown, so a later merge never detaches it
- one function decides what may leave the machine: `share_set()`. Every copy of a
  hash must be under Media\Communal; never-classified is held, not assumed safe
- no adult or unclear-age nudity ever ships; a child alone (the bath) may; only
  Krish's per-file `share = yes` releases an adult hold, never `intimate` or sexual
- the Python seed and the cloud's own Drive sync apply the SAME nudity rule,
  proven by one shared case table (`nudity_cases.json`)
- every image byte comes from a share-set hash; a video frame only with its own verdict
- the queue's side comes from the group's photographs, never from who is playing
- answers carry an id made on the phone: a retry is the same row, never a second
- "I don't know" is one player's skip, never a decline for everyone
- the app may write only person / unidentifiable (cluster) and place / approx_year
  (file, share-set hashes only); anything else is refused at the API AND at ingest
- the seed reconciles; a Drive listing that looks broken removes nothing
- nothing younger than the 10-minute undo window is pulled into the journal

## Code
| file | role |
|---|---|
| `stages/13_app/cloud_enrich.py` | THE writer of the index, from Drive alone: classify, hold, embed, place, faces, clusters, groups, queue, people, receipt |
| `stages/13_app/share_set.py` | the one rule for what may leave the library machine |
| `stages/13_app/seed_index.py` | the optional BRIDGE for when D: is connected: library knowledge up, with a watermark |
| `stages/13_app/pull_answers.py` | optional, with the bridge: app answers into the journal, older than the undo window |
| `stages/13_app/cloud.py` | Supabase REST and storage, keys from the environment only |
| `stages/13_app/chain_app_sync.ps1` | nightly: pull, merge, rebuild, seed |

The phone app itself lives in `web/` (Next.js on Vercel, project root `web`),
outside `stages/` because `npm install` on Windows writes `.ps1` and `.py`
files into `node_modules` that this contract would then try to own. It holds
the gate, the screens, a read-only Drive health check, and the schema
(`web/supabase/migrations/`). The index itself is written by `cloud_enrich.py`
from `.github/workflows/archives-enrich.yml`. Its tests run
under Node: `npm test` (vitest) and `npm run e2e` (Playwright, three phone
widths, synthetic family only).

## Tests
- `tests/test_app_cloud.py` (needs a Postgres: `TEST_PG_DSN`)
- `tests/test_app_share_set.py`
- `tests/test_app_sync.py`
- `tests/test_game_ingest.py`
- also `web/tests/*.test.ts` (vitest) and `web/e2e/*.spec.ts` (Playwright), which run under Node

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 44 | every share rule is watched refusing, not only passing | `test:tests/test_app_share_set.py:nobody has seen reject is indistinguishable from no filter` |
| 45 | embeddings and face vectors are joined by hash or (image, face_index), never by position | `code:stages/13_app/seed_index.py:never by position`, `test:tests/test_app_sync.py:joined by key, never by position` |
| 52 | "I don't know" is recorded as that player's skip, so nobody is asked twice | `code:web/lib/data.ts:export async function skip` |
| 57 | the cloud copy is reconciled on every run; a broken listing removes nothing | `code:stages/13_app/seed_index.py:RECONCILE, NOT APPEND`, `test:tests/test_app_cloud.py:an empty listing removed nothing` |
| 72 | a new cluster id clears every id already handed out, even with the counter lost | `code:stages/13_app/cloud_enrich.py:A NEW ID MUST CLEAR EVERY ID ALREADY HANDED OUT`, `test:tests/test_app_cloud.py:the next id still clears every k-id` |
| 74 | the queue uses build_game's verdicts: the latest answer per merge group decides | `test:tests/test_game_ingest.py:the latest answer wins` |
