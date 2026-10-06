-- 0010: photographs from the owner's Personal folder come into the family app
-- when someone the owner chose is clearly in them (Krish, 2026-10-06).
--
-- The owner's Personal folder holds his own life, and much of it is the
-- family's too. A Personal photograph comes in when a person the owner ticked
-- is clearly in it. The owner and his partner never count (the names the
-- private rules already ignore, migration 0008): a photograph of just them, or
-- just one of them, stays out. With 'personal_strict' on (sync_state), it comes
-- in only if EVERYONE clearly in it is ticked or one of those two - so someone
-- the app does not know, who can never be ticked, keeps a photograph out.
--
-- THE CHOICES ARE PRIVATE. This repository is public, so the ticked names, the
-- folder and the switch live only in the database (personal_people, sync_state
-- 'personal_folder' and 'personal_strict'); this file holds the mechanism.
--
-- stages/13_app/cloud_enrich.py looks at each Personal file once: Drive's own
-- rendering, the faces in it, and the face group each one belongs to
-- (personal_seen.subjects, cluster ids). Names are resolved HERE, when asked,
-- so a face the family names tomorrow, or a person ticked tomorrow, changes
-- the verdict without looking at the file again. A file that qualifies then
-- goes through everything a new Communal file does - the library's three
-- passes, the nudity rule, the private rules, the whole-video check - and one
-- that stops qualifying is hidden again (hidden_by = 'rule:personal').

create table if not exists personal_people (
  name  text primary key            -- a recognised person whose presence brings a Personal photograph in
);
alter table personal_people enable row level security;
revoke all on personal_people from anon, authenticated, public;

create table if not exists personal_seen (
  drive_id  text primary key,
  rel_path  text not null,
  subjects  text[] not null default '{}',   -- per face clearly in it: its cluster id, '' when it matches nobody
  status    text not null check (status in ('seen', 'error')),
  tries     int not null default 1,
  at        timestamptz not null default now()
);
alter table personal_seen enable row level security;
revoke all on personal_seen from anon, authenticated, public;

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
per as (
  select ps.drive_id, ps.rel_path,
    count(n.drive_id) as faces,
    count(*) filter (where n.name in (select name from personal_people)) as ticked,
    count(*) filter (where n.drive_id is not null and (n.name is null
                     or (n.name not in (select name from personal_people) and n.name not in (select name from us))))
      as others
  from personal_seen ps left join named n on n.drive_id = ps.drive_id
  where ps.status = 'seen'
  group by ps.drive_id, ps.rel_path
)
select drive_id, rel_path, faces, ticked, others,
  ticked > 0 and (others = 0 or coalesce((select value from sync_state where key = 'personal_strict'), 'true') <> 'true')
    as qualifies
from per;

revoke all on personal_verdicts from anon, authenticated, public;
