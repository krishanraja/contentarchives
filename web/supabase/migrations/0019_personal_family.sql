-- 0019: a Personal photograph comes in when the family is in it, or when it
-- was taken while the owner was with them (Krish, 2026-10-23: "this app only
-- reads from my personal library the media that is either with my family or
-- was taken when I was with my family").
--
-- Two changes to 0010's rule:
--
--   1. WHO COUNTS is worked out, not ticked: anyone the family has named in a
--      visible Communal photograph (photo_people, 0012), so a person named
--      tomorrow counts tomorrow. The owner and his partner still never count
--      (private_rules 'ignore'), and personal_blocked keeps anyone out by name.
--      sync_state 'personal_who' = 'ticked' goes back to the ticked list
--      (personal_people), the old rule, with one switch.
--
--   2. NEARBY: a photograph with nobody counted in it still comes in when it
--      was taken within 'personal_window_minutes' (default 120) of one that
--      qualifies by its people - the venue, the food, the view, the owner on
--      his own that afternoon - but only when every face clearly in it is the
--      owner or his partner, or there is none. That holds whatever
--      'personal_strict' says: a stranger always keeps a nearby photograph out.
--      Only an exact time counts (personal_seen.taken_at, the camera's clock or
--      a timestamp in the file's name); a day or a year alone is never nearby.
--
-- As in 0010, the names, the folder and the switches live only in the
-- database; this file holds the mechanism. A nearby photograph then meets every
-- rule a Communal file does (nudity, private places, the whole-video check).

create table if not exists personal_blocked (
  name  text primary key            -- a person who never brings a Personal photograph in
);
alter table personal_blocked enable row level security;
revoke all on personal_blocked from anon, authenticated, public;

alter table personal_seen add column if not exists taken_at timestamptz;
create index if not exists personal_seen_taken on personal_seen (taken_at);

create or replace view personal_counted with (security_invoker = true) as
with us as (select name from private_rules where kind = 'ignore'),
who as (select coalesce((select value from sync_state where key = 'personal_who'), 'communal') as v),
named as (
  select distinct pp.name from photo_people pp
  join photos p on p.hash = pp.hash
  where p.rel_path like 'Media/Communal/%' and p.visible and pp.name is not null
    and (select v from who) <> 'ticked'
  union
  select name from personal_people where (select v from who) = 'ticked'
)
select n.name from named n
where n.name not in (select name from us)
  and n.name not in (select name from personal_blocked);

revoke all on personal_counted from anon, authenticated, public;

create or replace view personal_verdicts with (security_invoker = true) as
with face as (
  select ps.drive_id, nullif(x.cid, '') as cid
  from personal_seen ps cross join lateral unnest(ps.subjects) as x(cid)
  where ps.status = 'seen'
),
named as (
  select f.drive_id, f.cid, g.name
  from face f
  left join clusters c on c.cluster_id = f.cid
  left join group_names g on g.group_id = c.group_id
),
us as (select name from private_rules where kind = 'ignore'),
counted as materialized (select name from personal_counted),
per as (
  select ps.drive_id, ps.rel_path, ps.taken_at,
    count(n.drive_id) as faces,
    count(*) filter (where n.name in (select name from counted)) as ticked,
    count(*) filter (where n.drive_id is not null and (n.name is null
                     or (n.name not in (select name from counted) and n.name not in (select name from us))))
      as others
  from personal_seen ps left join named n on n.drive_id = ps.drive_id
  where ps.status = 'seen'
  group by ps.drive_id, ps.rel_path, ps.taken_at
),
fam as materialized (
  select per.*, ticked > 0 and (others = 0
    or coalesce((select value from sync_state where key = 'personal_strict'), 'true') <> 'true') as family
  from per
),
win as (select make_interval(mins => coalesce(
  (select value from sync_state where key = 'personal_window_minutes')::int, 120)) as w),
anchor as materialized (select taken_at from fam where family and taken_at is not null)
select f.drive_id, f.rel_path, f.faces, f.ticked, f.others,
  f.family or coalesce(n.near, false) as qualifies,
  case when f.family then 'family' when n.near then 'nearby' end as why
from fam f
left join lateral (
  select true as near
  where not f.family and f.others = 0 and f.taken_at is not null
    and exists (select 1 from anchor a, win
                where a.taken_at between f.taken_at - win.w and f.taken_at + win.w)
) n on true;

revoke all on personal_verdicts from anon, authenticated, public;
