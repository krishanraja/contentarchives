-- 0009: a video plays in the app only after the whole of it has been judged
-- (Krish, 2026-10-06: "We also need videos to actually be able to play").
--
-- Until now a video was shown as one still, and only that still had been
-- judged. Playing it shows every frame, so every frame is judged first:
-- stages/13_app/cloud_enrich.py videos() downloads the video from Drive, has
-- the library's sensitivity pass watch all of it (Gemini, one frame a second,
-- the most revealing moment decides), and records the verdict here. The
-- /video route streams only a video whose row says 'ok'. A video that fails is
-- hidden everywhere, still and all (hidden_by = 'rule:video-check'), and is
-- never shown again unless Krish brings it back himself.
--
--   ok          judged whole and clear: it plays
--   held        judged and failed, or the model would not look: hidden
--   unplayable  a format a phone's browser cannot play (old tapes, MPEG-1/2,
--               3GP, MPEG-4 part 2) or too big to judge: its still stays,
--               nothing is spent on it
--   error       not judged this time; tried again on a later run, three times

create table if not exists video_checks (
  hash     text primary key references photos (hash) on delete cascade,
  status   text not null check (status in ('ok', 'held', 'unplayable', 'error')),
  reason   text,                    -- fixed words from the rule, never the model's own
  mime     text,                    -- what the phone is told it is, for 'ok'
  seconds  int,
  verdict  jsonb,                   -- nudity / subject_age / sexual: category words only
  usd      numeric(10, 5),
  tries    int not null default 1,
  at       timestamptz not null default now(),
  check (status <> 'ok' or mime is not null)
);

alter table video_checks enable row level security;
revoke all on video_checks from anon, authenticated, public;
