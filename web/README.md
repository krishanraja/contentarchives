# archives.krishraja.com

The family's Communal photographs on a phone: find them, and tell us who, where
and roughly when. Built for grandparents. Owned by `stages/13_app/STAGE.md`.

## How it fits together

```
Google Drive  My Drive/ContentLibrary/Media/Communal   the photographs (always on)
      │  read-only service account, that folder only
      ▼
Vercel (this folder)  ──  Supabase project "archives"   the index + the family's answers
      ▲                         ▲
      │ daily cron: new Drive    │ seed (when the library learns more) / pull (answers -> journal)
      │ files classified         │
      │                   library machine: stages/13_app/*.py, nightly chain_app_sync.ps1 (optional)
```

The app never needs the library machine to be on. The machine makes answers
permanent in `answers.csv` and sends new knowledge up when it is.

## Develop and test (synthetic family only)

```bash
npm install
# a local Postgres 16 with pgvector, then:
psql -f supabase/test/shim.sql -f supabase/migrations/0001_archives.sql
cp .env.example .env.local      # DATABASE_URL, ACCESS_CODE, SESSION_SECRET, IMAGE_SOURCE=fixture
npm run seed:fixtures            # cartoon photos of made-up people - never real ones
npm run dev
npm test                         # vitest: parser, gate, cookie, nudity-rule parity, prompt drift, sync
npm run e2e                      # Playwright at 360 / 390 / 430 px: floor, axe, every flow vs the stored row
```

## Going live: the order, and who does what

Each step marked **approval** is an external change Claude makes only after
Krish says yes to that step.

1. **approval** Create the Supabase project `archives` (Pro org, about $10/month)
   and apply `supabase/migrations/0001_archives.sql`.
2. **Krish** Google Cloud: create a service account with the Drive API enabled,
   download its JSON key. In Drive, **share only** `ContentLibrary/Media/Communal`
   with the service account's email as **Viewer**. Note the folder id from its URL.
3. **approval** Create the Vercel project (root directory `web`) and set the
   environment, by name only (values never pass through chat or the repo):
   `DATABASE_URL` (Supabase pooler, transaction mode), `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, `ACCESS_CODE`, `SESSION_SECRET` (32+ random
   bytes), `SESSION_VERSION=1`, `IMAGE_SOURCE=drive`,
   `GOOGLE_SERVICE_ACCOUNT_JSON`, `DRIVE_COMMUNAL_FOLDER_ID`,
   `DRIVE_REL_PREFIX=Media/Communal`, `GOOGLE_API_KEY_ARCHIVES` (a separate,
   quota-capped Gemini key), `CRON_SECRET`, optional `ALERT_WEBHOOK_URL`.
4. **Krish, on the library machine** (Claude cannot reach D:):
   ```powershell
   $env:SUPABASE_URL = "..."; $env:SUPABASE_SERVICE_ROLE_KEY = "..."   # this shell only
   python stages\13_app\share_set.py                 # read the held-out reasons
   python stages\13_app\seed_index.py                # dry run: read every count
   python stages\13_app\seed_index.py --check-frames # judge video face frames (Gemini, a few $)
   python stages\13_app\seed_index.py --apply        # upload; exits 1 unless the cloud's count matches
   ```
   Add `app: players: [...]` to `D:\_PhotoAudit\profile.yaml` first: those are
   the names on the "Who are you?" screen.
5. Trigger the Drive sync once (`/api/cron/drive-sync` with the cron secret): it
   binds every seeded photo to its Drive file by md5 and path.
6. **approval** Attach `archives.krishraja.com` (krishraja.com's DNS is on Vercel).
7. **Krish** Arm the nightly catch-up: `pwsh -File guards\arm.ps1 -Chain chain_app_sync.ps1`.
8. Retire Bharti's claude.ai artifact game, so two front ends never answer the same faces.

## Safety, in one place

- Only `share_set()` decides what leaves the machine; the cloud's own sync uses
  the same nudity rule (`stages/13_app/nudity_cases.json` is read by both test
  suites). No adult nudity ships; a child alone in the bath may; Krish alone
  releases a genuine family moment, per file, with `share = yes`.
- Anyone can tap **This photo shouldn't be here**: it is hidden for everyone at
  once. Bring one back in the database: `update photos set hidden = false where hash = '...'`.
- Change the code: set `ACCESS_CODE` and bump `SESSION_VERSION` - everyone signs in again.
- Answers are in `answers` until pulled; `status` says new / undone / ingested / refused (with the reason).
