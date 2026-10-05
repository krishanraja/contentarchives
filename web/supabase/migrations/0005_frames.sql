-- 0005: a video face is shown only on a frame of its own, judged before it is shown.
--
-- Krish, 2026-10-04: "it is imperative there is no sensitive nudity in this".
-- The library found 25,454 faces in video frames that no one ever judged frame
-- by frame (APP-FRAME-SENSITIVITY.csv never existed), so none could be shown -
-- and 942 of the 1,071 faces the library flagged "ask someone else" are seen
-- only in a video. stages/13_app/cloud_enrich.py now pulls that one frame from
-- the video on Drive, finds the same person in it, judges the frame with the
-- library's own sensitivity prompt, and stores it here only if it passes.
-- Every attempt is recorded, so a frame is judged once and never re-judged.

create table if not exists frames (
  key     text primary key,               -- the face key (faces.key) this frame shows
  status  text not null check (status in ('ok', 'held', 'noface', 'error')),
  jpeg    bytea,                          -- only when status = 'ok'
  w       int,
  h       int,
  verdict jsonb,                          -- nudity / subject_age / sexual: category words only
  at      timestamptz not null default now(),
  check ((status = 'ok') = (jpeg is not null))
);

alter table frames enable row level security;
revoke all on frames from anon, authenticated;
