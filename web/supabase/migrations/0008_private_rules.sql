-- 0008: photographs the owner keeps private never appear, unless someone else
-- in the family is recognised in them (Krish, 2026-10-06).
--
-- Some of the shared folder's photographs come from the owner's own life -
-- particular places and periods - and are not the family's to see. The rule:
-- a photograph that matches a private place, a private period, a private
-- person, or private words is hidden, UNLESS a recognised family member other
-- than the people the owner names as not counting is in it.
--
-- THE RULES THEMSELVES ARE PRIVATE. This repository is public, so the places,
-- dates and names live only in the database (private_rules), never in git;
-- this file holds the mechanism and nothing else.
--
-- Hidden here means hidden everywhere at once: search, browse, the photo and
-- face routes, "Who is this?" and "Where and when?" all read photos.visible.
-- The rule only ever hides (hidden_by = 'rule:private') and only ever un-hides
-- what it hid itself - a photograph a person hid stays hidden. It runs at the
-- end of every worker run, so a new photograph is judged before anyone sees it.

create table if not exists private_rules (
  id          serial primary key,
  kind        text not null check (kind in ('place', 'period', 'person', 'words', 'ignore')),
  pattern     text,                 -- place: matched against place, region and path; words: against the description
  from_at     timestamptz,          -- period: taken from this moment ...
  to_at       timestamptz,          -- ... until this one
  countries   text[],               -- period: only these countries (null: any) ...
  unplaced    boolean not null default false,   -- ... and photographs with no country at all
  name        text,                 -- person: a name whose photographs with nobody else are private;
                                    -- ignore: a name that does not count as "someone else in the family"
  check (kind not in ('place', 'words') or pattern is not null),
  check (kind <> 'period' or (from_at is not null and to_at is not null)),
  check (kind not in ('person', 'ignore') or name is not null)
);
alter table private_rules enable row level security;
revoke all on private_rules from anon, authenticated, public;

-- What overrides the rules, also private:
--   allow       a place that is ALWAYS fine (pattern, matched against place,
--               region and path): no rule hides a photograph taken there
--   family_min  "someone else in the family" means someone recognised in at
--               least n photographs OUTSIDE the private places and periods -
--               so friends who only ever appear inside them do not count
create table if not exists private_overrides (
  id       serial primary key,
  kind     text not null check (kind in ('allow', 'family_min')),
  pattern  text,
  n        int,
  check (kind <> 'allow' or pattern is not null),
  check (kind <> 'family_min' or n is not null)
);
alter table private_overrides enable row level security;
revoke all on private_overrides from anon, authenticated, public;

-- dry => count only. Returns how many photographs the rules hide now, how
-- many they hid before and no longer match (shown again), and how many they
-- cover in all. One statement: who is recognised in each photograph is
-- worked out once (photo_people is costly), and no table is created or removed.
create or replace function apply_private_rules(dry boolean default false)
returns table (hidden_now bigint, shown_again bigint, covered bigint)
language sql
set search_path = public
as $$
  with pp as materialized (select distinct x.hash, x.name from photo_people x),
  ign as (select name from private_rules where kind = 'ignore'),
  -- the private places and periods themselves
  scope as materialized (
    select p.hash from photos p
    where exists (select 1 from private_rules r where r.kind = 'place'
                  and (coalesce(p.place, '') ~* r.pattern or coalesce(p.region, '') ~* r.pattern
                       or coalesce(p.rel_path, '') ~* r.pattern))
       or exists (select 1 from private_rules r where r.kind = 'period'
                  and p.taken_at >= r.from_at and p.taken_at < r.to_at
                  and (r.countries is null or p.country = any(r.countries)
                       or (r.unplaced and coalesce(p.country, '') = '')))),
  -- who counts as someone else in the family: not ignored, and seen often
  -- enough outside the private places and periods
  family as (
    select pp.name from pp
    where pp.name not in (select name from ign) and pp.hash not in (select hash from scope)
    group by pp.name
    having count(*) >= coalesce((select max(n) from private_overrides where kind = 'family_min'), 1)),
  others as (select distinct pp.hash from pp where pp.name in (select name from family)),
  hit as (
    select p.hash from photos p
    where (p.hash in (select hash from scope)
       or exists (select 1 from pp join private_rules r on r.kind = 'person' and r.name = pp.name
                  where pp.hash = p.hash)
       or exists (select 1 from private_rules r where r.kind = 'words'
                  and coalesce(p.description, '') ~* r.pattern
                  and exists (select 1 from pp where pp.hash = p.hash and pp.name in (select name from ign))))
      and not exists (select 1 from private_overrides o where o.kind = 'allow'
                      and (coalesce(p.place, '') ~* o.pattern or coalesce(p.region, '') ~* o.pattern
                           or coalesce(p.rel_path, '') ~* o.pattern))
  ),
  priv as materialized (select hash from hit where hash not in (select hash from others)),
  up as (
    update photos p set hidden = true, hidden_by = 'rule:private', hidden_at = now()
    where not dry and p.hash in (select hash from priv) and not p.hidden
    returning 1),
  down as (
    update photos p set hidden = false, hidden_by = null, hidden_at = null
    where not dry and p.hidden_by = 'rule:private' and p.hash not in (select hash from priv)
    returning 1)
  select
    case when dry then (select count(*) from photos p where p.hash in (select hash from priv) and not p.hidden)
         else (select count(*) from up) end,
    case when dry then (select count(*) from photos p where p.hidden_by = 'rule:private' and p.hash not in (select hash from priv))
         else (select count(*) from down) end,
    (select count(*) from priv)
$$;
revoke all on function apply_private_rules(boolean) from anon, authenticated, public;
