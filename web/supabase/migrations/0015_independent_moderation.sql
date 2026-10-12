-- 0015: an independent, resumable sexual-content audit of everything the app
-- can show. The primary sensitivity gate is Gemini; this second pass uses a
-- separately trained provider and records every still and sampled video frame.
--
-- Only already-visible material is sent to the second provider. A positive
-- result hides the item immediately. Errors and missing samples never count as
-- clear, and a killed run resumes from the individual sample it last committed.

alter table snapshots drop constraint if exists snapshots_kind_check;
alter table snapshots add constraint snapshots_kind_check
  check (kind in ('seed', 'drive-sync', 'independent-moderation'));

create table if not exists independent_moderation (
  hash               text not null references photos (hash) on delete cascade,
  model              text not null,
  actual_model       text,
  media              text not null check (media in ('photo', 'video')),
  status             text not null check (status in ('pending', 'ok', 'held', 'error')),
  expected_samples   int not null default 0 check (expected_samples >= 0),
  checked_samples    int not null default 0 check (checked_samples >= 0),
  held_samples       int not null default 0 check (held_samples >= 0),
  max_sexual_score   double precision,
  reason             text,              -- fixed category words only
  tries              int not null default 1,
  at                 timestamptz not null default now(),
  primary key (hash, model),
  check (checked_samples <= expected_samples),
  check (held_samples <= checked_samples)
);

create table if not exists independent_moderation_samples (
  hash          text not null references photos (hash) on delete cascade,
  model         text not null,
  sample_key    text not null,           -- still | fps:<ordinal> | scene:<milliseconds>
  actual_model  text,
  status        text not null check (status in ('ok', 'held', 'error')),
  sexual        boolean,
  sexual_score  double precision,
  reason        text,                    -- fixed category/error word only
  tries         int not null default 1,
  at            timestamptz not null default now(),
  primary key (hash, model, sample_key),
  check (sexual_score is null or (sexual_score >= 0 and sexual_score <= 1)),
  check (status = 'error' or sexual is not null)
);

create index if not exists independent_moderation_status
  on independent_moderation (model, status);
create index if not exists independent_moderation_samples_status
  on independent_moderation_samples (model, status);

alter table independent_moderation enable row level security;
alter table independent_moderation_samples enable row level security;
revoke all on independent_moderation, independent_moderation_samples
  from anon, authenticated, public;
