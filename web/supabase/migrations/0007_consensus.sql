-- 0007: everyone's answer counts; nobody's answer overwrites anybody else's.
--
-- Krish, 2026-10-05: "make sure ... each person's classification does not over
-- ride each other, and that if someone misspells, it handles that too". Until
-- now a face's name was simply the LATEST answer from anyone, so a second
-- relative's guess silently replaced the first's.
--
--   * every answer is kept (answers is insert-only, as before);
--   * a person's own later answer replaces their OWN earlier one, never anyone
--     else's: each person has one vote per face;
--   * the name shown is the one most people gave; a tie goes to the name given
--     first. Spellings are folded first (case, spacing, punctuation, Unicode
--     form), so "asha raja" and "Asha  Raja." are one vote for one name;
--   * a tie between different answers is CONTESTED: the face stays in the queue
--     for people who have not answered it, until someone breaks the tie;
--   * "needs identifying" (the library's "ask someone else") is not a vote for
--     a name: alone, it keeps the face asked, first.

-- one spelling key for a name or a place: Unicode NFKC, lower case, letters and
-- digits only, single spaces
create or replace function name_key(t text) returns text
language sql immutable parallel safe set search_path = pg_catalog as $$
  select btrim(regexp_replace(lower(normalize(coalesce(t, ''), NFKC)), '[^[:alnum:]]+', ' ', 'g'))
$$;

-- Every view is replaced in place (group_names keeps its columns and gains
-- "contested" at the end), so nothing is dropped and this file can run twice.

-- each person's latest answer on a face group (on any of its clusters)
create or replace view group_votes with (security_invoker = true) as
with wm as (select coalesce(max(watermark), 'epoch'::timestamptz) as t from snapshots where kind = 'seed'),
latest as (
  select distinct on (c.group_id, a.who) c.group_id, a.who, a.field, a.value, a.at
  from answers a
  join clusters c on c.cluster_id = a.target, wm
  where a.scope = 'cluster' and a.status in ('new', 'ingested') and a.at > wm.t
  order by c.group_id, a.who, a.at desc
)
select group_id, who, field, value, at,
       case when field = 'person' then name_key(value)
            when field = 'unidentifiable' then '#unidentifiable' end as k
from latest;

create or replace view group_names with (security_invoker = true) as
with spell as (
  select group_id, k, value, count(*) as c, min(at) as f
  from group_votes where k is not null group by group_id, k, value
),
best_spell as (   -- the spelling most voters used for that answer; a tie goes to the first given
  select distinct on (group_id, k) group_id, k, value as spelling from spell order by group_id, k, c desc, f
),
tally as (
  select v.group_id, v.k, count(*) as n, min(v.at) as first_at, b.spelling
  from group_votes v join best_spell b on b.group_id = v.group_id and b.k = v.k
  where v.k is not null
  group by v.group_id, v.k, b.spelling
),
ranked as (
  select tally.*,
         row_number() over (partition by group_id order by n desc, first_at) as r,
         lead(n) over (partition by group_id order by n desc, first_at) as runner_up
  from tally
),
top as (select * from ranked where r = 1),
asked as (
  select group_id, bool_or(field = 'needs_identifying') as ask_others from group_votes group by group_id
),
groups as (
  select group_id, max(name) as seed_name from clusters group by group_id
)
select g.group_id,
       case when top.k is not null and top.k <> '#unidentifiable' then top.spelling
            when top.k is null and not coalesce(asked.ask_others, false) then g.seed_name end as name,
       -- settled: one answer leads outright (a name, or "not one person"), or
       -- nobody has answered and the library named it, and nobody asked again
       coalesce(top.k is not null and (top.runner_up is null or top.n > top.runner_up), false)
         or (top.k is null and g.seed_name is not null and not coalesce(asked.ask_others, false)) as answered,
       coalesce(asked.ask_others, false) and top.k is null as flagged,
       coalesce(top.runner_up is not null and top.n = top.runner_up, false) as contested
from groups g
left join top on top.group_id = g.group_id
left join asked on asked.group_id = g.group_id;

create or replace view photo_people with (security_invoker = true) as
select p.hash, unnest(p.people) as name from photos p
union
select ch.hash, g.name from cluster_hashes ch
  join group_names g on g.group_id = ch.group_id
  where g.name is not null;

-- the answers that are in the running on a contested face, for the next person
create or replace view group_contest with (security_invoker = true) as
with spell as (
  select group_id, k, value, count(*) as c, min(at) as f
  from group_votes where k is not null and k <> '#unidentifiable' group by group_id, k, value
),
tally as (
  select distinct on (group_id, k) group_id, k, value as spelling,
         sum(c) over (partition by group_id, k) as n
  from spell order by group_id, k, c desc, f
)
select t.group_id, t.spelling as name, t.n
from tally t join group_names g on g.group_id = t.group_id and g.contested;

create index if not exists answers_target_scope on answers (target) where scope = 'cluster';
create index if not exists answers_hashes on answers using gin (hashes) where scope = 'file';

revoke all on group_votes, group_names, photo_people, group_contest from anon, authenticated;
revoke all on function name_key(text) from anon, authenticated, public;
