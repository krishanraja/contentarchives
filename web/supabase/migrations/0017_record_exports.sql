-- 0017: the family's record, frozen every night (stages/13_app/export_record.py).
--
-- Krish, 2026-10-16: "I expect all this to be done automatically in the future
-- we just use the app. The external D (currently F) Drive should just be a
-- backup, nothing should rely on this external drive." Supabase already backs
-- this whole database up each night. This adds a frozen, portable copy: what
-- the family said, the library journal, and a catalogue of every photograph
-- with how to find it on both copies (Drive and the backup drive) and
-- everything known about it - the input for a future re-sort of both copies.
-- One gzip'd CSV per name per night, the newest 14 nights kept. The library
-- machine copies the newest onto the backup drive whenever that drive is
-- connected (stages/13_app/backup_to_drive.py); nothing waits on it.

create table if not exists record_exports (
  day      date not null,
  name     text not null check (name in ('answers', 'journal', 'catalogue')),
  rows     integer not null,          -- data rows, the header not counted
  bytes    integer not null,          -- of the gzip
  sha256   text not null,             -- of the gzip
  body     bytea not null,            -- gzip of a UTF-8 CSV, header row first
  made_at  timestamptz not null default now(),
  primary key (day, name)
);

-- Private: only the writer (the nightly workflow) and the service role read it.
alter table record_exports enable row level security;
revoke all on record_exports from anon, authenticated;
