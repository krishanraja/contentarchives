-- 0004: the library's knowledge, imported once and kept in the cloud for good.
--
-- Krish, 2026-10-05: "make it such that this is never reliant on a local
-- machine or external drive again". stages/13_app/cloud_enrich.py imports the
-- library export (stages/13_app/LIBRARY-EXPORT.md) into these tables; from then
-- on this database, not a local drive, is the system of record.

-- A photograph the app may show is one bound to a Drive file and not hidden.
-- A library row whose Drive file is missing (or gone) keeps everything the
-- library knew about it and re-binds by md5 when the file appears; until then
-- no page may show it. One column, so no query can forget half the rule.
alter table photos add column if not exists visible boolean
  generated always as (drive_id is not null and not hidden) stored;
create index if not exists photos_md5 on photos (md5);
create index if not exists photos_visible on photos (visible);

-- A face the library measured on a thumbnail that is missing, or on a video
-- frame no one has judged for sensitivity, has no box: it groups and finds
-- people, and is never drawn.
alter table faces alter column bbox drop not null;
-- The size of the picture a library box was measured on (its thumbnail). When
-- the photo binds to Drive, a box whose picture is not the shape Drive shows
-- (a thumbnail made without turning the photo upright) is never drawn.
alter table faces add column if not exists measured_w int;
alter table faces add column if not exists measured_h int;

-- The library's merge groups were decided by people (CLUSTER-MERGES.csv). The
-- cloud never re-merges two of them; its own clusters may join one.
alter table clusters add column if not exists pinned boolean not null default false;

-- Everything the library holds out, kept for good: a file that reaches Drive
-- later with one of these md5s (or, for a row with no md5, this path) is held
-- without being classified, shown or re-judged.
create table if not exists library_held (
  key      text primary key,             -- 'md5:<md5>', or 'path:<rel_path>' when no md5 is known
  hash     text,
  md5      text,
  rel_path text,
  reason   text not null                 -- a category word, never a description
);

-- The library's answers journal, verbatim and whole: every answer Krish and
-- Bharti gave, corrections included. The cloud's copy of the one record that
-- no amount of re-running can rebuild.
create table if not exists journal (
  id         uuid primary key,           -- uuid5 of the row's own content (LIBRARY-EXPORT.md)
  at         timestamptz not null,
  who        text not null,
  scope      text not null,
  target     text not null,
  field      text not null,
  value      text not null,
  confidence real,
  note       text
);
create index if not exists journal_target on journal (target);

-- "needs_identifying" is the library's "I don't know who this is - ask
-- someone": it is an answer the journal keeps, and it puts a face IN the
-- queue rather than taking it out (build_game.wanted). The app itself still
-- writes only person / unidentifiable (lib/data.ts).
alter table answers drop constraint if exists answers_check;
alter table answers add constraint answers_check check (
  (scope = 'cluster' and field in ('person', 'unidentifiable', 'needs_identifying')) or
  (scope = 'file' and field in ('place', 'approx_year'))
);

-- The LAST answer for a group decides (build_game.verdicts): a name names it,
-- "not the same person" or a decline closes it, and a later "needs
-- identifying" re-opens it and asks it first.
drop view if exists photo_people;
drop view if exists group_names;
drop view if exists cluster_names;

create view cluster_names with (security_invoker = true) as
with wm as (select coalesce(max(watermark), 'epoch'::timestamptz) as t from snapshots where kind = 'seed'),
latest as (
  select distinct on (target) target as cluster_id, field, value, at
  from answers, wm
  where scope = 'cluster' and status in ('new', 'ingested') and at > wm.t
  order by target, at desc
)
select c.cluster_id, c.group_id,
       case when l.field = 'person' then l.value
            when l.field is not null then null
            else c.name end as name,
       l.field as answered,                -- the field of this cluster's latest answer, if any
       l.at
from clusters c left join latest l on l.cluster_id = c.cluster_id;

create view group_names with (security_invoker = true) as
select group_id,
       case when last_field = 'person' then last_name
            when last_field is null then fallback_name
            else null end as name,
       coalesce(last_field in ('person', 'unidentifiable'), false)
         or (last_field is null and fallback_name is not null) as answered,
       coalesce(last_field = 'needs_identifying', false) as flagged
from (
  select group_id,
         (array_agg(answered order by at desc) filter (where answered is not null))[1] as last_field,
         (array_agg(name order by at desc) filter (where answered is not null))[1] as last_name,
         (array_agg(name order by cluster_id) filter (where answered is null and name is not null))[1] as fallback_name
  from cluster_names
  group by group_id
) s;

create view photo_people with (security_invoker = true) as
select p.hash, unnest(p.people) as name from photos p
union
select ch.hash, g.name from cluster_hashes ch
  join group_names g on g.group_id = ch.group_id
  where g.name is not null;

alter table library_held enable row level security;
alter table journal enable row level security;
revoke all on library_held, journal from anon, authenticated;
revoke all on cluster_names, group_names, photo_people from anon, authenticated;
