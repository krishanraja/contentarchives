# archives.krishraja.com

The family's Communal photographs on a phone: find them, and tell us who, where
and roughly when. Built for grandparents. Owned by `stages/13_app/STAGE.md`.

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

**Nothing depends on D: or any PC.** Ruling (Krish, 2026-10-04): the index is
built from Drive in the cloud. When the library machine is connected it can
optionally add what only it knows (`seed_index.py`, the bridge) and copy answers
into the journal (`pull_answers.py`); the app never waits for it.

## Develop and test (synthetic family only)

```bash
npm install
# a local Postgres 16 with pgvector, then:
psql -f supabase/test/shim.sql -f supabase/migrations/0001_archives.sql \
     -f supabase/migrations/0002_harden.sql -f supabase/migrations/0003_cloud.sql
cp .env.example .env.local      # DATABASE_URL, ACCESS_CODE, SESSION_SECRET, IMAGE_SOURCE=fixture
npm run seed:fixtures            # cartoon photos of made-up people - never real ones
npm run dev
npm test                         # vitest: parser, gate, cookie, nudity-rule parity, prompt drift
npm run e2e                      # Playwright at 360 / 390 / 430 px: floor, axe, every flow vs the stored row
```

## Running it

- **The index**: `.github/workflows/archives-enrich.yml`. Secrets it needs (GitHub →
  Settings → Secrets and variables → Actions): `DATABASE_URL` (Supabase transaction
  pooler), `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_API_KEY_ARCHIVES`,
  `DRIVE_COMMUNAL_FOLDER_ID`. A manual run takes a file budget; the nightly run is
  off until the repository variable `ARCHIVES_ENRICH` is `on`, and setting it to
  anything else pauses it without a commit. Each run stops at `SPEND_CAP_USD` ($60)
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
- **The Communal share**: the service account is a **Viewer** on that one folder,
  and the folder's general access is **Restricted**. Nothing else is shared with it.
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
