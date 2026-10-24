-- 0021: a photograph shown the right way up (Krish, 2026-10-24, on a print
-- photographed sideways: "There are still photos not rotated up the right way").
--
-- The app already obeys a file's own orientation tag (sharp .rotate()). A phone
-- photo of a print taken sideways has no tag to obey: the picture itself is on
-- its side. So each photograph carries a TURN, degrees clockwise applied after
-- its tag, that makes it upright:
--   * the worker asks the library's own vision model once per photograph
--     (turn_checked_at), and a face that reads well only the other way round
--     overrules it (stages/13_app/cloud_enrich.py orient());
--   * anyone in the family can turn a photo from its own screen, and their turn
--     is never overruled by the model (turn_source = 'family', logged in turns).
--
-- A face box is a fraction of the picture it was measured on, so each face
-- records the turn it was measured at (faces.turn); the app turns a box from
-- that to the photo's turn when it draws it. Faces read sideways match people
-- badly, so the worker reads a turned photo's faces again the right way up
-- (faces_turn = the turn they were last read at; faces_reread once the cloud
-- has replaced the library's own boxes). A face found again where one was keeps
-- that face's cluster, and so its name.

alter table photos add column if not exists turn int not null default 0;
alter table photos add column if not exists turn_source text;
alter table photos add column if not exists turn_checked_at timestamptz;
alter table photos add column if not exists faces_turn int not null default 0;
alter table photos add column if not exists faces_reread boolean not null default false;
alter table faces add column if not exists turn int not null default 0;

do $$ begin
  alter table photos add constraint photos_turn_check check (turn in (0, 90, 180, 270));
exception when duplicate_object then null; end $$;
do $$ begin
  alter table photos add constraint photos_turn_source_check check (turn_source in ('model', 'family'));
exception when duplicate_object then null; end $$;

-- the photos still to be asked, and those whose faces were read another way round
create index if not exists photos_turn_todo on photos (hash) where turn_checked_at is null and media = 'photo';
create index if not exists photos_faces_stale on photos (hash) where turn <> faces_turn;

-- who turned what, and which way it ended up
create table if not exists turns (
  id    bigint generated always as identity primary key,
  who   text not null,
  hash  text not null,
  turn  int not null check (turn in (0, 90, 180, 270)),
  at    timestamptz not null default now()
);
alter table turns enable row level security;
revoke all on turns from anon, authenticated, public;
