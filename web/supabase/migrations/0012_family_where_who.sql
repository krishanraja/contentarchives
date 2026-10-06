-- 0012: what the family says about WHERE a photograph was taken, and WHO is in
-- it, wins over what the library guessed (Krish, 2026-10-06: "everything needs
-- to be 10x more intuitive" - a wrong place or a wrong name must be put right
-- from the photograph itself, as the year is in 0011).
--
-- WHERE. Until now a family answer about the place was written only when a
-- photograph had no place, so a wrong one could never be corrected. The
-- family's settled answer (each person's latest answer one vote) now lives in
-- family_place and wins on the photograph, in the place search, the place
-- chips and the list of places.
--   The owner's private rules (0008) see it too, but only to HIDE: a place the
--   family gives can bring a photograph inside a private place, never take one
--   out - the always-fine places are matched against the library's place and
--   path alone, so no answer typed on a phone can un-hide anything.
--
-- WHO. A photograph's people are the library's names and its faces' names
-- (photo_people). Now each person's latest answer about one name on one
-- photograph is a vote - "in_photo" or "not_in_photo" - and the votes decide:
-- more "not" than "in" takes a name off that photograph, more "in" than "not"
-- adds one. Only that photograph: the face group, and every other photograph
-- of that person, is untouched.

alter table photos add column if not exists family_place text;

-- the two new answers about who is in ONE photograph
alter table answers drop constraint if exists answers_check;
alter table answers add constraint answers_check check (
  (scope = 'cluster' and field in ('person', 'unidentifiable', 'needs_identifying')) or
  (scope = 'file' and field in ('place', 'approx_year', 'in_photo', 'not_in_photo'))
);

update photos p set family_place = p.place
where p.family_place is null and p.place is not null
  and exists (select 1 from answers o where o.scope = 'file' and o.field = 'place'
              and o.status in ('new', 'ingested') and o.hashes @> array[p.hash]
              and name_key(o.value) = name_key(p.place));

create index if not exists answers_file_people on answers (field) where scope = 'file' and field in ('in_photo', 'not_in_photo');

create or replace view photo_people with (security_invoker = true) as
with base as (
  select p.hash, unnest(p.people) as name from photos p
  union
  select ch.hash, g.name from cluster_hashes ch
    join group_names g on g.group_id = ch.group_id
    where g.name is not null
),
votes as (
  select distinct on (a.who, h, name_key(a.value)) h as hash, a.value as name, a.field
  from answers a cross join lateral unnest(a.hashes) h
  where a.scope = 'file' and a.field in ('in_photo', 'not_in_photo') and a.status in ('new', 'ingested')
  order by a.who, h, name_key(a.value), a.at desc
),
tally as (
  select hash, name_key(name) as k, min(name) as name,
         count(*) filter (where field = 'in_photo') as yes,
         count(*) filter (where field = 'not_in_photo') as no
  from votes group by hash, name_key(name)
),
taken_off as (select hash, k from tally where no > yes)
select b.hash, b.name from base b
where not exists (select 1 from taken_off o where o.hash = b.hash and o.k = name_key(b.name))
union
select t.hash, t.name from tally t where t.yes > t.no;

create or replace function search_photos(
  q_embedding extensions.vector(768) default null,
  q_text      text default null,
  q_people    text[] default null,
  q_place     text default null,
  q_year_from int default null,
  q_year_to   int default null,
  q_limit     int default 60,
  q_offset    int default 0
) returns table (hash text, score real, total bigint)
language sql stable
set search_path = public, extensions
as $$
  with wanted as materialized (
    select pp.hash
    from photo_people pp
    where q_people is not null
      and lower(pp.name) in (select lower(w) from unnest(q_people) w)
    group by pp.hash
    having count(distinct lower(pp.name)) =
           (select count(distinct lower(w)) from unnest(q_people) w)
  ), base as (
    select p.* from photos p
    where not p.hidden and p.drive_id is not null
      and (q_people is null or p.hash in (select w.hash from wanted w))
      and (q_place is null or
           coalesce(p.family_place, coalesce(p.place,'') || ' ' || coalesce(p.region,'') || ' ' ||
           coalesce(p.country,'')) ilike '%' || q_place || '%')
      and (q_year_from is null or p.when_year >= q_year_from)
      and (q_year_to is null or p.when_year <= q_year_to)
  ), ranked as (
    select b.hash,
      case
        when q_embedding is not null and b.embedding is not null
          then (1 - (b.embedding <=> q_embedding))::real
        when q_text is not null
          then ts_rank(b.fts, websearch_to_tsquery('simple', q_text))::real
        else 0::real
      end as score,
      b.when_year, b.taken_at
    from base b
    where q_embedding is not null
       or q_text is null
       or b.fts @@ websearch_to_tsquery('simple', q_text)
  )
  select r.hash, r.score, count(*) over () as total
  from ranked r
  order by
    case when q_embedding is null and q_text is null then 0 else -r.score end,
    r.when_year desc nulls last, r.taken_at desc nulls last
  limit q_limit offset q_offset
$$;

revoke all on function search_photos(extensions.vector, text, text[], text, int, int, int, int) from anon, authenticated, public;

create or replace function apply_private_rules(dry boolean default false)
returns table (hidden_now bigint, shown_again bigint, covered bigint)
language sql
set search_path = public
as $$
  with pp as materialized (select distinct x.hash, x.name from photo_people x),
  ign as (select name from private_rules where kind = 'ignore'),
  -- the private places and periods themselves; a place the family gave counts
  scope as materialized (
    select p.hash from photos p
    where exists (select 1 from private_rules r where r.kind = 'place'
                  and (coalesce(p.place, '') ~* r.pattern or coalesce(p.region, '') ~* r.pattern
                       or coalesce(p.rel_path, '') ~* r.pattern or coalesce(p.family_place, '') ~* r.pattern))
       or exists (select 1 from private_rules r where r.kind = 'period'
                  and p.taken_at >= r.from_at and p.taken_at < r.to_at
                  and (r.countries is null or p.country = any(r.countries)
                       or (r.unplaced and coalesce(p.country, '') = '')))),
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
      -- always-fine places: the library's place and path only, never a family answer
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
