-- 0016: sign in with a code sent by email, once Krish has said yes (Krish,
-- 2026-10-15). The family code no longer lets anyone new in. A new person
-- gives their email and first name; Krish is emailed and says yes or no on a
-- page of the app; then a six-digit code is emailed to them, and the phone
-- stays signed in for a year from its last visit.
--
-- Addresses and names are family data: they live only in these tables, never
-- in this public repository, its commits or its logs. A code is never stored,
-- only a keyed hash of it.

create table if not exists access_people (
  email      text primary key
             check (email = lower(btrim(email)) and email like '_%@_%' and char_length(email) <= 254),
  name       text not null check (char_length(name) between 2 and 40),
  status     text not null default 'asked' check (status in ('asked', 'yes', 'no')),
  asked_at   timestamptz not null default now(),
  decided_at timestamptz,
  tries      int not null default 0 check (tries >= 0)   -- wrong codes since the last good one
);

create table if not exists access_codes (
  id         bigserial primary key,
  email      text not null references access_people (email) on delete cascade,
  code_hash  text not null,
  sent_at    timestamptz not null default now(),
  expires_at timestamptz not null,
  used_at    timestamptz
);
create index if not exists access_codes_email on access_codes (email, expires_at);

-- One row per email sent, never its contents: what caps how many go out.
create table if not exists access_sends (
  id      bigserial primary key,
  kind    text not null check (kind in ('code', 'ask')),
  email   text not null,
  ip_hash text not null,
  at      timestamptz not null default now()
);
create index if not exists access_sends_at on access_sends (at);
create index if not exists access_sends_email on access_sends (email, at);

alter table access_people enable row level security;
alter table access_codes enable row level security;
alter table access_sends enable row level security;
revoke all on access_people, access_codes, access_sends from anon, authenticated;
revoke all on sequence access_codes_id_seq, access_sends_id_seq from anon, authenticated;
