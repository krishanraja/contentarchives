# archives.krishraja.com

The family's photographs and videos on a phone: find them, and tell us who, where
and roughly when. Built for grandparents. Owned by `stages/13_app/STAGE.md`.

As of 2026-10-11 the live app shows 18,726 photographs and 6,718 videos (read
from the live database the day this was written; `photos where visible`).

## How it fits together

```
Google Drive: the Communal folder        the photographs (always on)
      │  read-only service account, that folder only
      ├──────────────────────────────┐
      ▼                              ▼
GitHub Actions, daily            Vercel (this folder)
stages/13_app/cloud_enrich.py    the app: reads the index, records answers,
THE ONE WRITER of the index:     shows photos straight from Drive
describe, hold, faces, groups,        │
queue, people, receipt                │
      └──────────►  Supabase "archives"  ◄──┘
                    the index + the family's answers
```

**The library, once.** Everything the library machine learned (descriptions, faces,
the merge groups people decided, every answer in the journal) arrives once as
`archives-library.sqlite` in Krish's Drive, shared with the service account only,
and the worker imports it (`stages/13_app/LIBRARY-EXPORT.md`). From then on
Supabase is the system of record. A photo is shown only when `photos.visible`:
bound to a Drive file and not hidden. A face seen only in a video is shown on a
frame of its own, pulled from Drive and judged before anyone sees it (`frames`).

**Nothing depends on D: or any PC.** Ruling (Krish, 2026-10-04): the index is
built from Drive in the cloud. When the library machine is connected it can
optionally add what only it knows (`seed_index.py`, the bridge) and copy answers
into the journal (`pull_answers.py`); the app never waits for it.

## What it does, screen by screen

- **Gate** (`/gate`): one family code for everyone (`ACCESS_CODE`, case and
  spaces ignored). Wrong tries are counted per hashed IP in `gate_attempts` and
  lock out; a lockout can alert `ALERT_WEBHOOK_URL` if that is set. Then **Who
  are you?** (`/who`): a name kept only in a signed cookie, so answers carry it.
  The phone also remembers that name in its own signed cookie (`arch_me`, 400
  days), so typing the code again later goes straight home as the same person;
  it opens nothing without the code, and "Not ...? Tap here" on Home changes it.
  Every other route is behind both (`middleware.ts`).
- **Home**: how many photos and videos there are, and three tiles.
- **Find photos & videos** (`/find`): one search box (typed, or said with the
  phone browser's own speech recognition where it has one), All / Photos /
  Videos as one joined switch, and Who / Where / When / Say as four buttons
  that narrow whatever the search started from, each choice with its count
  (`search_photos` and `search_facets`, migration 0013). Words are ranked by
  meaning with Gemini embeddings when `GOOGLE_API_KEY_ARCHIVES` is set, by
  plain word match otherwise. The state is the URL (`?q=`, `?type=`, `?pick=`).
- **A photo or video** (`/photo/[hash]`): Who, Where and When, each a button
  that puts it right (the family's answer wins); a video plays only once it has
  been watched whole and judged clear (`video_checks`), otherwise its still.
  Anyone can hide a photo for everyone.
- **Who is this?** (`/help`) and **Where and when?** (`/story`): the naming
  games; every answer is one person's vote in `answers`.
- Sizes: every control at least 48px, body text 18px, no text under 14px
  (Ruling, Krish, 2026-10-11); nothing on any screen scrolls.

## Everything it has access to

Names only. Values, ids, the family code and the project's identifiers are
never written in this public repository.

| System | What | Access | Used by |
|---|---|---|---|
| Google Drive | the Communal folder | service account, **Viewer**, that folder | the app (images, video, health check) and the nightly writer |
| Google Drive | the owner's Personal folder | the same service account, **Viewer**; the folder id is kept in the database (`sync_state`), not in env | the nightly writer only: a Personal photo is shown only while someone the owner chose is clearly in it (migration 0010) |
| Google Gemini | `gemini-3.1-flash-lite` (describe, judge videos), `gemini-embedding-001` (search by meaning) | the app's own capped key, `GOOGLE_API_KEY_ARCHIVES` | the nightly writer (spend capped per run) and the app (one embedding per words search) |
| Supabase project "archives-london" (London, eu-west-2; moved from Sydney 2026-10-12) | Postgres: the index and the family's answers | `DATABASE_URL` (transaction pooler) | the app reads and records answers; the writer writes the index |
| Supabase Storage | private bucket `media`: cut face crops and frames | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | the app |
| Vercel project "archives" | hosting, region `lhr1` (London), root `web`, production branch `main` | deploys from GitHub on every push to `main` | the app |
| GitHub Actions | `.github/workflows/archives-enrich.yml`, nightly 01:17 UTC (overnight in London) | repository secrets below | the writer, `stages/13_app/cloud_enrich.py` |

**The app's environment (Vercel, all "sensitive" ones are write-only and cannot
be read back, even by the owner):** `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `ACCESS_CODE`, `SESSION_SECRET`, `SESSION_VERSION`,
`IMAGE_SOURCE=drive`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DRIVE_COMMUNAL_FOLDER_ID`,
`DRIVE_REL_PREFIX`, `GOOGLE_API_KEY_ARCHIVES`, `CRON_SECRET`; optional
`ALERT_WEBHOOK_URL`.

**The writer's secrets (GitHub Actions):** `DATABASE_URL`,
`GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_API_KEY_ARCHIVES`,
`DRIVE_COMMUNAL_FOLDER_ID`; repository variables `ARCHIVES_ENRICH` (`off`
pauses the nightly run) and `ARCHIVES_VIDEOS_PER_RUN`.

**Database functions the app calls:** `search_photos` (nine arguments since
0013; `q_media` last and optional) and `search_facets`. Neither can be run by
`anon` or `authenticated`: only the server's own connection reaches them.
`search_photos_0012` is the pre-0013 search, renamed aside when 0013 went
live because the live migration tool held back a DROP; nothing calls it.
Migrations 0001-0012 were applied to the live database as plain SQL; only
`0012a` and `0013_facets` appear in its migration history, so check the live
functions themselves rather than that history.

## Develop and test (synthetic family only)

```bash
npm install
# a local Postgres 16 with pgvector, then the shim and EVERY migration in order:
psql -f supabase/test/shim.sql
for m in supabase/migrations/*.sql; do psql -v ON_ERROR_STOP=1 -f "$m"; done
cp .env.example .env.local      # DATABASE_URL, ACCESS_CODE, SESSION_SECRET, IMAGE_SOURCE=fixture
npm run seed:fixtures            # cartoon photos of made-up people - never real ones
npm run dev
npm test                         # vitest: parser, facets' links, gate, cookie, nudity-rule parity, prompt drift
npm run e2e                      # Playwright at 360 / 390 / 430 px: floor, axe, every flow vs the stored row;
                                 # noscroll.spec.ts walks every screen at 19 sizes
# the database side, against the same local Postgres:
TEST_PG_DSN=postgresql://... python tests/test_app_cloud.py   # from the repo root
```

## Running it

- **The index**: `.github/workflows/archives-enrich.yml`. Secrets it needs (GitHub →
  Settings → Secrets and variables → Actions): `DATABASE_URL` (Supabase transaction
  pooler), `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_API_KEY_ARCHIVES`,
  `DRIVE_COMMUNAL_FOLDER_ID`. A manual run takes a file budget; the nightly run
  (01:17 UTC) is on, and setting the repository variable `ARCHIVES_ENRICH` to
  `off` pauses it without a commit. Each run stops at `SPEND_CAP_USD` ($60)
  or `MAX_MINUTES`, then still rebuilds the queue and writes a receipt to
  `snapshots` (`kind = 'drive-sync'`: counts, dollars, seconds).
- **The public log prints numbers only.** The repository is public, so no path,
  name, description or folder id may reach it; `tests/test_app_cloud.py` fails if one does.
- **The app**: Vercel project `archives`, root `web`, production branch `main`.
  Environment, by name only: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `ACCESS_CODE`, `SESSION_SECRET`, `SESSION_VERSION`, `IMAGE_SOURCE=drive`,
  `GOOGLE_SERVICE_ACCOUNT_JSON`, `DRIVE_COMMUNAL_FOLDER_ID`, `DRIVE_REL_PREFIX`,
  `GOOGLE_API_KEY_ARCHIVES`, `CRON_SECRET`.
- **Health check** (read-only): `GET /api/cron/drive-sync` with
  `Authorization: Bearer $CRON_SECRET` returns the folder's file count on Drive,
  what is indexed, held and queued, and the last run's receipt.
- **The Drive shares**: the service account is a **Viewer** on the Communal
  folder and on the owner's Personal folder, and nothing else; both folders'
  general access is **Restricted**.
- Retire Bharti's claude.ai artifact game, so two front ends never answer the same faces.

## Safety, in one place

- One nudity rule, `nudity_hold()`, used by the cloud writer, the optional seed
  and the app (`stages/13_app/nudity_cases.json` is read by both test
  suites). No adult nudity ships; a child alone in the bath may; Krish alone
  releases a genuine family moment, per file, with `share = yes`.
- Anyone can tap **This photo shouldn't be here**: it is hidden for everyone at
  once. Bring one back in the database: `update photos set hidden = false where hash = '...'`.
- Change the code: set `ACCESS_CODE` and bump `SESSION_VERSION` - everyone signs in again.
- Answers live in `answers` (insert-only; Supabase backs it up daily); `status` says
  new / undone / ingested / refused (with the reason).
