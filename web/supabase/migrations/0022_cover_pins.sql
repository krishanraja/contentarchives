-- 0022: a person's Home face can be chosen by hand (Krish, 2026-10-24, on the
-- faces on Home: "Pick more flattering cover photos for Jyoti, Krish, and Bhasker").
--
-- The worker picks each person's cover by detection score and face size, which
-- says nothing about whether the picture flatters them, and it deletes and
-- refills `people` every night, so a cover written straight into `people` would
-- be gone by morning. A pin lives here instead. The nightly rebuild
-- (stages/13_app/cloud_enrich.py rebuild()) uses a person's pin while that face
-- is still on a photograph anyone can see, and falls back to its own pick when
-- it is not (the photo was hidden or left Drive), so a pin can never show a face
-- the app would not otherwise draw.
--
-- No foreign key to faces: a face row can be replaced by a later run, and a pin
-- must survive that to be checked again, not be deleted with it.

create table if not exists cover_pins (
  name      text primary key,
  face_key  text not null,
  pinned_by text not null,
  at        timestamptz not null default now()
);
alter table cover_pins enable row level security;
revoke all on cover_pins from anon, authenticated, public;
