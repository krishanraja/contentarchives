-- The index is built from Google Drive in the cloud (stages/13_app/cloud_enrich.py),
-- not seeded from a PC. Krish, 2026-10-04: "Nothing about the D drive exists for
-- this session" - no step may depend on D: or any machine being on.
--
-- Faces are detected and clustered by the cloud worker, so a face carries its
-- own embedding and a cluster its centroid. And because groups are recomputed
-- as clusters merge, a NAME belongs to a CLUSTER: an answer's target is the
-- cluster id the person was shown (frozen, never renumbered), and a group's
-- name is read from whichever of its clusters was named. A later merge can
-- then never detach an answer from the faces it was about.

alter table faces alter column group_id drop not null;
alter table faces add column if not exists cluster_id text;
alter table faces add column if not exists embedding extensions.vector(512);
alter table faces add column if not exists share real;          -- face size / frame short edge (is_subject)
create index if not exists faces_cluster on faces (cluster_id);

alter table clusters add column if not exists centroid extensions.vector(512);
alter table clusters add column if not exists n int not null default 0;

alter table photos add column if not exists lat double precision;
alter table photos add column if not exists lon double precision;

drop view if exists photo_people;
drop view if exists group_names;

-- the latest live answer per CLUSTER (since the last seed, if one ever ran)
create view cluster_names with (security_invoker = true) as
with wm as (
  select coalesce(max(watermark), 'epoch'::timestamptz) as t
  from snapshots where kind = 'seed'
), latest as (
  select distinct on (target) target as cluster_id, field, value, at
  from answers, wm
  where scope = 'cluster' and status in ('new','ingested') and at > wm.t
  order by target, at desc
)
select c.cluster_id, c.group_id,
       case when l.field = 'person' then l.value
            when l.field is not null then null
            else c.name end as name,
       l.field as answered, l.at
from clusters c left join latest l on l.cluster_id = c.cluster_id;

create view group_names with (security_invoker = true) as
select group_id,
       (array_agg(name order by at desc nulls last) filter (where name is not null))[1] as name,
       bool_or(answered is not null or name is not null) as answered
from cluster_names
group by group_id;

create view photo_people with (security_invoker = true) as
select p.hash, unnest(p.people) as name from photos p
union
select ch.hash, g.name from cluster_hashes ch
join group_names g on g.group_id = ch.group_id
where g.name is not null;

revoke all on cluster_names, group_names, photo_people from anon, authenticated;
