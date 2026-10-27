# archives.krishraja.com

The family's photographs and videos on a phone: find them, and tell us who, where
and roughly when. Built for grandparents. Owned by `stages/13_app/STAGE.md`.

A snapshot, not a current figure: on 2026-10-11 the live app showed 18,726
photographs and 6,718 videos (read from the live database that day; `photos where
visible`). The count has changed since. Home shows the current numbers, and the
health check under "Running it" reports what is indexed, held and queued.

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
built from Drive in the cloud. Ruling (Krish, 2026-10-16): the cloud is the
record, H: (Google Drive) holds the photographs, and the external drive is only
a backup. Every night the cloud freezes every answer and a catalogue of every
photograph (`stages/13_app/export_record.py`, `CATALOGUE.md`); when the backup
drive is plugged in, under any letter, `chain_app_sync.ps1` copies that and any
new photographs from H: onto it. The app never waits for any of it.

## What it does, screen by screen

- **Signing in** (`/gate`; self-serve since 2026-10-23, Krish: "I don't need
  to approve every new user"): a person types their email, and the first time
  their first name too, and is emailed a link (`/in`) with a six-digit code
  beside it, both good for 30 minutes. Nobody waits for Krish. The link's page
  only shows a button and the tap signs in, because a mail scanner opening the
  link must not spend the code; the code is for a phone whose link opens in
  another browser (an installed home-screen app). Krish can still stop
  someone (`status = 'no'`); an address left waiting for his yes from before
  2026-10-23 is let in the next time it signs in. Every step is a plain form
  posted to `/api/access`, so it works before the page's script arrives, and
  the email typed is kept in a signed cookie (`arch_ask`, 30 days). Addresses
  and names live only in the database (`access_people`, migration 0016); a
  code is kept only as a hash keyed by `SESSION_SECRET` (`access_codes`).
  Every cap is checked and recorded in one transaction that holds a lock, so
  a burst of requests sent at once meets it one at a time: an email a minute
  (unless no code still works) and six an hour per address, thirty an hour per
  network and two hundred in all (`access_sends`), which is also what bounds
  new sign-ups; at most two codes working at once; five wrong tries, after
  which every code for that address stops until a new one is sent. Wrong
  codes count per hashed IP in `gate_attempts` and lock out, and a
  lockout can alert `ALERT_WEBHOOK_URL`. Signed in by email, a phone stays in
  for **a year from its last visit**: `middleware.ts` signs the session again
  once it is a day old (a session from the retired family code carries no
  `via` and keeps the end it was given). The
  name comes with the email; **Who are you?** (`/who`) is now reached by "Not
  ...? Tap here" on Home, for a phone passed round the family, and the phone
  remembers that name in its own signed cookie (`arch_me`). Every other route is
  behind signing in (`middleware.ts`).
- **Home** (faces first since 2026-10-23, Krish: "I prefer the home screen having
  all of our faces to choose from to start the exploration"): hello, a Sign out
  button top right, a search box, then the family's faces, each one a link to that
  person's photos. One face nobody has named sits among them with a "?" and
  "Who?", a different one on every visit, and it opens the naming game on that
  same face. "Who is this?" and "Where and when?" sit under the faces as two rows
  with what is left (`app/page.tsx`).
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
  Anyone can hide a photo for everyone, and anyone can tap **Turn** on a photo
  shown sideways (for everyone, and the model never overrules it; migration 0021).
- **Spelling** (`/spelling`, owner only, 404 for anyone else): each pair of known
  names that look like one person saved two ways, one at a time, for the owner to
  call the same person or two (migrations 0018 and 0020).
- **Who is this?** (`/help`) and **Where and when?** (`/story`): the naming
  games; every answer is one person's vote in `answers`. Who is this? shows
  when and where the photo was taken as a badge on it (the photo page's own
  rule: the family's answer, then the file's date, then the year folder), and
  **See all of it** opens the whole photo full screen without the ring's
  dimming, with the other photos from that day (`day_key`) a tap each: who is
  holding the baby is often in the next photo along (Krish, 2026-10-16).
- Sizes: every control at least 40px, body text 16px, no text under 14px
  (Ruling, Krish, 2026-10-23; 48px / 18px before); one raised button per
  screen, its next best action; nothing on any screen scrolls.

## Everything it has access to

Names only. Values, ids, the family's email addresses and the project's
identifiers are never written in this public repository.

| System | What | Access | Used by |
|---|---|---|---|
| Google Drive | the Communal folder | service account, **Viewer**, that folder | the app (images, video, health check) and the nightly writer |
| Google Drive | the owner's Personal folder | the same service account, **Viewer**; the folder id is kept in the database (`sync_state`), not in env | the nightly writer only: a Personal photo is shown only while someone the owner chose is clearly in it (migration 0010) |
| Google Drive | the folder "ContentArchives record" in the owner's My Drive | the same service account, **Editor on that one folder only**: it replaces the three files Krish owns there each night and can create, move or delete nothing | the nightly writer (`stages/13_app/export_record.py`) |
| OpenAI | image moderation, a pinned model, free | `OPENAI_API_KEY` (GitHub Actions secret) | the independent audit (`stages/13_app/independent_moderation.py`, `.github/workflows/archives-independent-moderation.yml`) over already-visible stills and playable-video frames only |
| Google Gemini | `gemini-3.1-flash-lite` (describe, judge videos), `gemini-embedding-001` (search by meaning) | the app's own capped key, `GOOGLE_API_KEY_ARCHIVES` | the nightly writer (spend capped per run) and the app (one embedding per words search) |
| Supabase project "archives-london" (London, eu-west-2; moved from Sydney 2026-10-12) | Postgres: the index and the family's answers | `DATABASE_URL` (transaction pooler) | the app reads and records answers; the writer writes the index |
| Supabase Storage | private bucket `media`: cut face crops and frames | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | the app |
| Resend | sends the sign-in links and codes, from a verified krishraja.com address | `RESEND_API_KEY` (sending only), `MAIL_FROM` | the app (`web/lib/mail.ts`) |
| Vercel project "archives" | hosting, region `lhr1` (London), root `web`, production branch `main` | deploys from GitHub on every push to `main` | the app |
| GitHub Actions | `.github/workflows/archives-enrich.yml`, nightly 01:17 UTC (overnight in London) | repository secrets below | the writer, `stages/13_app/cloud_enrich.py` |

**The app's environment (Vercel, all "sensitive" ones are write-only and cannot
be read back, even by the owner):** `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `SESSION_SECRET`, `SESSION_VERSION`,
`RESEND_API_KEY`, `MAIL_FROM`, `ACCESS_ADMIN_EMAIL`,
`IMAGE_SOURCE=drive`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DRIVE_COMMUNAL_FOLDER_ID`,
`DRIVE_REL_PREFIX`, `GOOGLE_API_KEY_ARCHIVES`, `CRON_SECRET`; optional
`ALERT_WEBHOOK_URL`. (`ACCESS_CODE`, the retired family code, is no longer read.)

**The writer's secrets (GitHub Actions):** `DATABASE_URL`,
`GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_API_KEY_ARCHIVES`,
`DRIVE_COMMUNAL_FOLDER_ID`; repository variables `ARCHIVES_ENRICH` (`off`
pauses the nightly run) and `ARCHIVES_VIDEOS_PER_RUN`. The independent audit
workflow also needs `OPENAI_API_KEY` and `DATABASE_URL` and
`GOOGLE_SERVICE_ACCOUNT_JSON`, and its scheduled run is off until the repository
variable `ARCHIVES_INDEPENDENT_AUDIT` is `on`.

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
cp .env.example .env.local      # DATABASE_URL, SESSION_SECRET, IMAGE_SOURCE=fixture, and for sign-in:
                                 # MAIL_SINK=/tmp/archives-mail.jsonl, ACCESS_ADMIN_EMAIL=admin@family.test
npm run seed:fixtures            # cartoon photos of made-up people - never real ones
npm run dev
npm test                         # vitest: parser, facets' links, sign-in, cookies, nudity-rule parity, prompt drift
set -a; . ./.env.local; set +a   # the e2e suite reads the emailed codes from MAIL_SINK and signs an old session
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
  `SESSION_SECRET`, `SESSION_VERSION`, `SESSION_SIGNED_OUT` (optional), `RESEND_API_KEY`, `MAIL_FROM`, `ACCESS_ADMIN_EMAIL`, `IMAGE_SOURCE=drive`,
  `GOOGLE_SERVICE_ACCOUNT_JSON`, `DRIVE_COMMUNAL_FOLDER_ID`, `DRIVE_REL_PREFIX`,
  `GOOGLE_API_KEY_ARCHIVES`, `CRON_SECRET`.
- **Health check** (read-only): `GET /api/cron/drive-sync` with
  `Authorization: Bearer $CRON_SECRET` returns the folder's file count on Drive,
  what is indexed, held and queued, and the last run's receipt.
- **The Drive shares**: the service account is a **Viewer** on the Communal
  folder and on the owner's Personal folder, and an **Editor** on exactly one
  other folder, "ContentArchives record" (the nightly copy of the family's
  record); it has no other access. The Communal and Personal folders' general
  access is **Restricted**.
- Retire Bharti's claude.ai artifact game, so two front ends never answer the same faces.

## Safety, in one place

- One nudity rule, `nudity_hold()`, used by the cloud writer, the optional seed
  and the app (`stages/13_app/nudity_cases.json` is read by both test
  suites). No adult nudity ships; a child alone in the bath may; Krish alone
  releases a genuine family moment, per file, with `share = yes`.
- Anyone can tap **This photo shouldn't be here**: it is hidden for everyone at
  once. Bring one back in the database: `update photos set hidden = false where hash = '...'`.
- Who can get in: anyone who signs in with their email (since 2026-10-23,
  no approval). To stop someone signing in again: `update access_people
  set status = 'no' where email = '...'`. A phone already signed in stays in
  until it goes a year unused; to sign every phone out, bump `SESSION_VERSION`.
  To sign ONE person out and leave everyone else in, add `Name=<unix seconds now>`
  to `SESSION_SIGNED_OUT` (comma-separated) and redeploy: their sessions signed
  before then stop working, and signing in again by email works as ever.
- Answers live in `answers` (insert-only; Supabase backs it up daily); `status` says
  new / undone / ingested / refused (with the reason). Only the app refuses: an
  answer the PC's journal could not take yet stays `new`, its reason beginning
  "library:", and `pull_answers.py` offers it again next run.
