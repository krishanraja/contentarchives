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
- Google Drive's Communal folder, read by the app's service account (Viewer)
- the owner's Personal folder, read by the same service account (Viewer), by
  the nightly writer only; its id lives in the database (`sync_state`), never here
- Resend, through the app's own sending key: the sign-in links and codes, and nothing else
- Gemini through the app's own capped key: describing and judging (the writer),
  one embedding per words search (the app)
- OpenAI image moderation through its own key: an independent, free second
  opinion over already-visible stills and playable-video frames only
- the full access inventory, by name only: `web/README.md` "Everything it has access to"

## Outputs
- the cloud index (Supabase): photos, faces, clusters, groups, queue, people -
  DERIVED, written by ONE writer, `cloud_enrich.py`, on GitHub Actions daily
- `independent_moderation` and `independent_moderation_samples`: durable,
  per-sample evidence for the independent visible-site audit
- the app's `answers` table: what the family said, the system of record until pulled
- `access_people`: who has signed in, and anyone Krish has stopped (addresses and names:
  family data, in the database only), with `access_codes` (hashes) and `access_sends`
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
- "I don't know" is one player's skip, never a decline for everyone, and never
  an exit: the face (or photo) goes to the back of THAT player's queue for 30 days
  and comes round again once they have seen the rest; a face two or more people
  did not know goes behind the others, still asked (Krish, 2026-10-05)
- nobody's answer overwrites anybody else's: each person's latest answer on a face,
  a place or a year is one vote; the most votes decide and a tie goes to the first
  given; a tie on a face is CONTESTED and stays asked, first, of people who have
  not answered it, with the answers in the running as the choices
  (`web/supabase/migrations/0007_consensus.sql`; a person is never asked a face
  they have already answered)
- case, spacing, punctuation and Unicode form are not spelling (`name_key` in SQL,
  `fold` in `web/lib/spelling.ts`: the same key); a near miss ("Meera Sha") is
  offered as "Did you mean Meera Shah?", one tap either way, never merged silently
- a name already saved two ways (one letter apart) is put right only by the
  owner, one pair at a time (`/spelling`, `web/lib/respell.ts`, migration 0018),
  and only as answers: his own vote on each face group, and "not in it / in it"
  on each photograph the library listed under the wrong spelling. Nothing is
  edited, a relative's vote is never rewritten for them, and a pair he called
  two people is not asked again (Krish, 2026-10-21). His "same" verdict maps every
  vote's spelling before it is counted (`group_votes`, migration 0020), so a wrong
  spelling a RELATIVE gave is put right too, instead of his answer only tying with
  theirs and sending the face back to the family as contested
- a place or year the library gave is never replaced by an app answer
- the cloud is the record, H: (Google Drive, `My Drive\ContentLibrary`) holds the
  photographs, and the external drive is only a backup (Krish, 2026-10-16: "nothing
  should rely on this external drive, everything should be able to be done on H
  drive"). Every night the cloud freezes the family's record and a catalogue of
  every photograph (`export_record.py`, CATALOGUE.md) with no PC; the backup drive
  is refreshed from that and from H: whenever it is plugged in, under any letter,
  and its absence fails nothing. Files are not moved: the app organises, and the
  catalogue carries what a later re-sort of both copies needs
- the service account reads Drive everywhere it is shared and writes to exactly one
  folder, "ContentArchives record" (Krish, 2026-10-16: "can we not do this in the
  cloud? My computer is not on 24 hours"): it replaces the contents of the three
  files Krish owns there each night, checked by the md5 Drive reports back, and can
  create, move or delete nothing (a service account has no Drive storage). The
  folder is found by name; no Drive id is ever committed or logged
- only the app refuses an app answer: the PC bridge (`pull_answers.py`) copies
  answers into the journal and, when the journal will not take one, leaves it
  `new` with a reason beginning "library:" and offers it again next run, because
  `refused` takes an answer out of every view in the app (learning 83)
- no screen of the app scrolls, on any device (Krish, 2026-10-05): every screen is
  one window tall, a photo takes the room its question leaves it, a list longer
  than its room turns like pages (`web/components/Fit.tsx`), and a phone on its
  side puts the photo beside the question. `web/e2e/noscroll.spec.ts` walks every
  screen in every state at 19 sizes a page really gets INSIDE a browser (the
  screen less its address bar and toolbars: 320x460 to 1920x960, upright and
  sideways, Krish's own phone at 412x748): nothing scrolls, every button is
  wholly on screen and is what a finger lands on, no words spill out of their box
  or sit on another box, and a photo stays big enough to recognise someone.
  Nothing is clipped to pass, and no box shrinks below its own words: if
  something ever did not fit, the page would scroll, never lay words over words
- photographs from places, periods or people the owner keeps private are hidden
  everywhere unless someone else in the family is recognised in them - "someone
  else" meaning a person seen often enough OUTSIDE those places and periods, so
  friends who only appear inside them do not count; a place marked always-fine
  overrides every rule (Krish, 2026-10-06). THE RULES ARE PRIVATE: they live only
  in the database (`private_rules`, `private_overrides`), never in this public
  repository, its commits or its logs; migration 0008 holds the mechanism, and the
  worker applies it every run before anything is rebuilt. It only ever un-hides
  what it hid itself (`hidden_by = 'rule:private'`)
- a video plays only after the WHOLE of it has been judged (Krish, 2026-10-06): its
  still was all that had been checked, and playing shows every frame. The worker
  (`videos()`, `--videos` per run: 0 from the command line, 3,000 a night in the workflow since Krish's go on 2026-10-06; it is a spend, measured at about $0.0007 a video) downloads it, has
  the library's sensitivity pass watch the picture (no sound) a frame a second in
  parts that cover every second, and the most revealing moment decides by the
  photograph's own rule. A part the model will not look at holds it; an unreadable
  answer is no verdict and is tried again, three times. A video that fails is hidden
  everywhere, still and all (`hidden_by = 'rule:video-check'`), and only Krish brings
  it back. The `/video` route streams a video only while `video_checks` says `ok`,
  in pieces of at most 3.5 MB; a format no phone plays keeps its still and costs
  nothing. Migration 0009 holds the states
- the independent audit never expands the exposure surface: it reads only rows
  already `visible`, checks the exact 1600px still the site can serve, and checks
  every playable video's picture at one frame per second plus scene changes. It
  uses a pinned OpenAI moderation model, separately from the Gemini publication
  gate. Every sample commits independently; missing frames, malformed answers,
  provider errors and interrupted work never count as clear. One sexual positive
  hides the whole item as `rule:independent-check`; only a person may release it.
  A playable video with no still from Drive or the site's own storage is cleared
  on its frames alone ("frames only") and looked at again every run in case a
  still appears; an unplayable one with no still on two runs is withheld as
  `rule:independent-unverifiable` (Krish, 2026-10-15).
  Hidden or held media is never sent to this provider. Migration 0015 holds the
  evidence, and `.github/workflows/archives-independent-moderation.yml` resumes it
- signing in (Krish, 2026-10-23: "I don't need to approve every new user";
  first set 2026-10-15): the shared family code lets nobody new in. A person
  types their email (and the first time a first name) and is emailed a link
  with a six-digit code beside it; nobody waits for Krish, and only his 'no'
  stops someone. The link only SHOWS a button, and the tap signs in, because
  mail scanners open every link in an email (`web/e2e/flows.spec.ts` "opening
  a sign-in link spends nothing"). A code is stored only as a hash keyed by the session secret,
  each kind of signed token opens only its own door (`web/tests/access.test.ts`),
  and every cap on sends and wrong tries is checked and recorded in one locked
  transaction, so a burst of requests sent at once meets it one at a time
  (`web/e2e/flows.spec.ts` "a burst of requests sent at once meets every limit
  one at a time"). Addresses and names live only in the database, never in
  this public repository, its commits or its logs. A phone signed in by email
  stays signed in for a year from its LAST visit (`web/middleware.ts` signs
  the session again once it is a day old); a session from the retired family
  code keeps the end it was given
- a photograph from the owner's Personal folder comes in only when the family is
  clearly in it, or it was taken while he was with them (Krish, 2026-10-06, widened
  2026-10-23). WHO COUNTS is anyone the family has named in a visible Communal
  photograph (`personal_counted`, migration 0019), minus a private block list
  (`personal_blocked`); `personal_who = 'ticked'` goes back to the ticked list. He
  and his partner never count, so a photograph of just them stays out on its own, and
  with the switch on everyone clearly in it must count or be one of them, so someone
  the app does not know keeps it out. NEARBY: a photograph with nobody counted in it
  comes in when it was taken within `personal_window_minutes` (default 120) of one
  that qualifies by its people, and only when every face clearly in it is him or his
  partner, or there is none - a stranger keeps a nearby photograph out whatever the
  switch says. Only an exact moment counts (`personal_seen.taken_at`: the camera's
  clock, or a timestamp in the file's name, `personal_time()`); a day or a year alone
  is never nearby, and a nearby photograph hides again when its anchor goes.
  THE CHOICES ARE PRIVATE: the names, the folder and the switches live only in the
  database (`personal_people`, `personal_blocked`, `sync_state`), never in this public repository. Each
  file is looked at once (faces only, no spend); names are resolved in the database
  when asked (`personal_verdicts`), so a later tick or a newly named face changes the
  verdict without looking again. Only what qualifies is described, and it then meets
  every rule a Communal file does (nudity, private places, whole-video check). It
  starts no new face for the family to name, it is hidden again the moment it stops
  qualifying (`hidden_by = 'rule:personal'`), and each folder's listing removes only
  its own files. Migration 0010 holds the mechanism. It shows only while it
  qualifies AS STORED too (a face's group can move between the look and the store:
  30 of the first 1,100 did), and a family's "not in it" for the ticked person counts
- a photograph is shown the right way up (Krish, 2026-10-24: "There are still photos
  not rotated up the right way"). Its own orientation tag is obeyed first; a print
  photographed sideways has none, so each photo carries a `turn` (degrees clockwise,
  migration 0021). The worker asks the library's vision model once per photograph
  (`orient()`), and where faces are found they decide the turn (`best_turn()`), the
  model only marking a photo worth the look; anyone can turn a photo from its own
  screen or from Who is this?, and that turn is never overruled (`turn_source =
  'family'`, logged in `turns`). A face box records the turn it was measured at
  (`faces.turn`) and is turned with its picture when drawn (`web/lib/turn.ts`); a
  turned photo's faces are read again the right way up (`reread()`), a face found
  where one was keeping that face's cluster and so its name, and a later library
  import never puts the sideways boxes back (`faces_reread`)
- when the family says when a photograph was taken, that is when it was taken
  (Krish, 2026-10-06: a file's date is often the day it was scanned or copied).
  Their settled answer (`family_when`, each person's latest answer one vote) wins
  over the file's date everywhere: the photo, the grid's badge, the search by year
  and decade, the year chips and the order of results, all through one computed
  column (`when_year`, migration 0011). The year under every photo is a button: a
  decade, then a year, and the photos the file dates to the same day can be put
  right in the same answer
- a person's Home face can be pinned by hand (Krish, 2026-10-24): `cover_pins` (migration 0022) is read by
  `cloud_enrich.py` `rebuild()` after it refills `people` each night, so a pin outlives the rebuild. A pin is used
  only while its face is on a visible photograph with a box (a missing or hidden face would break the
  `people.cover_face` key); otherwise the automatic pick stands. Pins are set by hand in the database, never by the app
- the family's WHERE and WHO win the same way (Krish, 2026-10-06): their settled
  place (`family_place`) shows and is searched instead of the library's, and each
  person's latest "in it" / "not in it" on one photograph is a vote that adds or
  takes off that name on that photograph only (`photo_people`, migration 0012).
  Under every photo Who, Where and When are three buttons that put them right. The
  owner's private rules see a family's place only to HIDE: an always-fine place is
  matched against the library's place and path alone, so nothing typed on a phone
  can un-hide a private photograph
- every size rule asks the space the page really has (`@container screen`), never
  the window (Krish, 2026-10-06): a phone's browser answers `@media (max-height)`
  as if its address bar were hidden, so a rule written that way did not fire on
  his phone and the home screen's words spilled over each other.
  `web/tests/style.test.ts` fails on any window-sized rule
- the size floor is two steps down from where it started (Krish, 2026-10-11:
  "everything is overly 'accessibility-friendly' right now"; 2026-10-23: "a
  little bit less for old people"): every control at least 40px tall, body
  text 16px, no text under 14px, contrast AA. Each screen raises exactly one
  filled button with a shadow, its next best action; everything else is flat.
  `floor()` in `web/e2e/helpers.ts` holds every screen of the flows to it at
  360, 390 and 430px; nothing goes below it
- a search narrows from wherever it starts (Krish, 2026-10-11: "if someone
  enters with a name, they should then be able to filter the time, content type,
  location or 'say' what they are actually looking for", and the same from a
  place). Every results screen offers the same four - Who, Where, When, Say - and
  All / Photos / Videos, whatever came first; each choice says how many it would
  give against every OTHER filter in force, so a chosen year still shows its
  neighbours (`search_facets`, migration 0013, read once per request: learning
  80). Words rank and never narrow the counts; "Who" offers who ELSE is in them.
  The state is the URL (`?q=`, `?type=`, `?pick=`), every choice a real link, so
  it works before the script arrives. A video is marked as one wherever it shows
  - a play mark and its length in the grid, "Video" on the picture itself - and
  keeps its year. `tests/test_app_cloud.py` "8f" and the flows in
  `web/e2e/flows.spec.ts` hold it
- the app may write only person / unidentifiable (cluster) and place / approx_year
  (file, share-set hashes only); anything else is refused at the API AND at ingest
- the seed reconciles; a Drive listing that looks broken removes nothing
- nothing younger than the 10-minute undo window is pulled into the journal
- the library's knowledge leaves this machine ONCE, through `export_library.py`,
  read-only on D:/F: and on H:\My Drive\ContentLibrary, and the export file never
  enters git: it carries family names and face embeddings and the repo is public
- a held-out file is NAMED in the export, not merely counted, so the cloud can
  keep it out; its reason is a category word and never a description
- the cloud imports the export once per distinct file and is then the system of
  record: nothing reads a local drive again (Krish, 2026-10-05)
- held wins every tie: a Drive file matching anything the library held out is
  held unseen, now and whenever it reappears (`library_held`); a second copy of a
  library photograph is held as a duplicate, never classified
- a library photo binds to Drive by MD5; by path only when the library knew no md5,
  because a changed file under the same name is a different file and is judged afresh
- a library row whose file leaves Drive is unbound, never deleted: what the library
  knew cannot be made again
- the library's merge groups are pinned: the cloud never merges two of them
- "needs identifying" is the library's "ask someone else": it keeps a face IN the
  queue, first, until an answer closes it (each person's latest answer is their vote)
- a face is drawn only with a box measured on a picture the shape Drive shows; video
  faces have never been judged frame by frame, so they group and find people and
  are never drawn
- a photo is shown only when `visible`: bound to a Drive file and not hidden
- a library box on a VIDEO was measured on the library's own frame grab, not the
  frame Drive shows: never drawn
- a video face is shown only on a frame of its own: pulled from the video on Drive
  at the library's timestamp, the same person found in it again by embedding, and
  cleared by the library's sensitivity pass on THAT frame; every attempt is kept
  (`frames`), so no frame is judged twice and a held one is never shown

## Code
| file | role |
|---|---|
| `stages/13_app/cloud_enrich.py` | THE writer of the index, from Drive alone: classify, hold, embed, place, faces, clusters, groups, queue, people, receipt |
| `stages/13_app/independent_moderation.py` | resumable independent audit of every visible still and every playable video's one-per-second and scene-change frames; positives hold immediately |
| `stages/13_app/share_set.py` | the one rule for what may leave the library machine |
| `stages/13_app/seed_index.py` | the optional BRIDGE for when D: is connected: library knowledge up, with a watermark |
| `stages/13_app/export_library.py` | the ONE-TIME carry: everything the library learned, into Drive as SQLite, to `LIBRARY-EXPORT.md` |
| `stages/13_app/pull_answers.py` | optional, with the bridge: app answers into the journal, older than the undo window |
| `stages/13_app/cloud.py` | Supabase REST and storage, keys from the environment only |
| `stages/13_app/chain_app_sync.ps1` | refreshes the BACKUP drive when it is plugged in, under any letter (found by its markers, mapped to D: for the run): pull, merge, rebuild, backup; seed only with `-Seed`, because a seed empties the cloud's faces and clusters and refills them from this library alone. No drive: a clean exit 0. The prompt to run it on demand: `stages/13_app/EXTERNAL-DRIVE-SYNC.md` |
| `stages/13_app/export_record.py` | nightly, in the cloud workflow: every answer, the journal and a catalogue of every photograph (CATALOGUE.md) frozen as gzip'd CSV in `record_exports`, 14 nights kept, read back and checked, and the same three files replaced in the Drive folder "ContentArchives record" (md5-checked), so a copy outside the database exists with no computer on |
| `stages/13_app/backup_to_drive.py` | the backup drive's refresh: the newest cloud export saved and sha256-checked, and every photograph H: has that the drive lacks copied and md5-checked against Drive's own; never overwrites, never deletes, --max-gb per run |

The phone app itself lives in `web/` (Next.js on Vercel, project root `web`),
outside `stages/` because `npm install` on Windows writes `.ps1` and `.py`
files into `node_modules` that this contract would then try to own. It holds
signing in (emailed links and codes), the screens, a read-only Drive health check, and the schema
(`web/supabase/migrations/`). The index itself is written by `cloud_enrich.py`
from `.github/workflows/archives-enrich.yml`. Its tests run
under Node: `npm test` (vitest) and `npm run e2e` (Playwright, three phone
widths, synthetic family only).

## Tests
- `tests/test_app_cloud.py` (needs a Postgres: `TEST_PG_DSN`)
- `tests/test_app_share_set.py`
- `tests/test_app_export.py`
- `tests/test_app_sync.py`
- `tests/test_backup_to_drive.py` - the backup drive is found by what is on it,
  never required, never overwritten, and every copy is checked against Drive's md5
- `tests/test_game_ingest.py`
- also `web/tests/*.test.ts` (vitest) and `web/e2e/*.spec.ts` (Playwright), which run under Node

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 44 | every share rule is watched refusing, not only passing | `test:tests/test_app_share_set.py:nobody has seen reject is indistinguishable from no filter` |
| 45 | embeddings and face vectors are joined by hash or (image, face_index), never by position | `code:stages/13_app/seed_index.py:never by position`, `test:tests/test_app_sync.py:joined by key, never by position`, `test:tests/test_app_export.py:carries ITS OWN embedding` |
| 52 | "I don't know" is recorded as that player's skip: it never declines a face for everyone, and it comes round again for them after the rest | `code:web/lib/data.ts:export async function skip`, `test:web/e2e/flows.spec.ts:I don't know comes back around`, `test:tests/test_app_cloud.py:a tie is kept, shows the first name given, and is asked first` |
| 57 | the cloud copy is reconciled on every run; a broken listing removes nothing | `code:stages/13_app/seed_index.py:RECONCILE, NOT APPEND`, `test:tests/test_app_cloud.py:an empty listing removed nothing` |
| 72 | a new cluster id clears every id already handed out, even with the counter lost | `code:stages/13_app/cloud_enrich.py:A NEW ID MUST CLEAR EVERY ID ALREADY HANDED OUT`, `test:tests/test_app_cloud.py:the next id still clears every k-id` |
| 74 | the queue uses build_game's verdicts: the latest answer per merge group decides | `test:tests/test_game_ingest.py:the latest answer wins` |
| 78 | a Personal photograph shows only while it qualifies as stored, judged after grouping | `code:stages/13_app/cloud_enrich.py:after group(): a new face's group is known only then`, `test:tests/test_app_cloud.py:a face stored as someone unknown, or a ticked name the family took off, keeps it out`, `test:tests/test_app_cloud.py:a photo whose person is known only once the run groups it shows on that same run` |
| 79 | picking frames is optional: its failure is rolled back and counted, and the private rules, video checks and receipt still run | `code:stages/13_app/cloud_enrich.py:extra: its failure must not stop the rules and checks after it`, `test:tests/test_app_cloud.py:a failure picking video frames still runs the private rules and writes the receipt` |
| 80 | a save reads the known names from a one-minute copy and checks only the answers given since; it never scans the library per tap | `code:web/lib/data.ts:per-save query must not scan the library`, `test:web/tests/memo.test.ts:a known name, however typed, never asks the database`, `test:web/tests/memo.test.ts:a name another phone gave a minute ago, missing from the kept list, is still that name` |
| 81 | every choice on the Find screen is fetched before it is tapped and marks itself pressed at once; a place name is read the same way in a link and in typed words | `code:web/components/Go.tsx:fetched before it is`, `test:web/tests/search.test.ts:every choice on the Find screen answers the tap at once`, `test:web/tests/search.test.ts:chosen from the list, it is found again in its own link` |
| 82 | a resumable cloud pass filters completed rows in one set query and fans out one-sample items through its bounded worker pool; it never pays one network round trip or one serial provider call per visible item | `code:stages/13_app/independent_moderation.py:Keep the resume filter in Postgres`, `code:stages/13_app/independent_moderation.py:write serially`, `test:tests/test_app_cloud.py:resume filtering is one set query`, `test:tests/test_app_cloud.py:independent photographs use the bounded worker pool` |
| 83 | the PC bridge never voids an app answer: a row the journal will not take stays `new` with a reason beginning "library:" and is offered again next run; a photograph the app shows counts as shared | `code:stages/13_app/pull_answers.py:THE LIBRARY NEVER VOIDS AN APP ANSWER`, `test:tests/test_app_sync.py:the library never refuses an app answer`, `test:tests/test_app_sync.py:the app's visible photographs among the targets` |
