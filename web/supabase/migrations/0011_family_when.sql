-- 0011: when the family says when a photograph was taken, that is when it was
-- taken (Krish, 2026-10-06).
--
-- "Oftentimes the metadata just reports on when the picture came into existence
-- on the computer, which might be completely wrong." A scan, a copy, a phone
-- restore: the date in the file is the day it was made, not the day the
-- picture was. Until now a family answer about the year was written only when
-- the photograph had no year at all, so a wrong date could never be put
-- right, and every screen showed the file's date first.
--
-- Now the family's settled answer (each person's latest answer is one vote,
-- as for places) lives in family_when - '1987' or '1980s' - and wins over the
-- file's date everywhere: what the photo says, the badge on the grid, the
-- search by year and decade, the year chips, and the order of results.
-- when_year is that one rule, computed once, so no query can forget it.

alter table photos add column if not exists family_when text;

alter table photos add column if not exists when_year int generated always as (
  case
    when family_when ~ '^[0-9]{4}' then substring(family_when from 1 for 4)::int
    when year is not null then year
    when approx_year ~ '^[0-9]{4}' then substring(approx_year from 1 for 4)::int
  end) stored;

create index if not exists photos_when_year on photos (when_year);

-- any year the family had already given (written to approx_year before this)
update photos p set family_when = p.approx_year
where p.family_when is null and p.approx_year is not null
  and exists (select 1 from answers o where o.scope = 'file' and o.field = 'approx_year'
              and o.status in ('new', 'ingested') and o.hashes @> array[p.hash]
              and name_key(o.value) = name_key(p.approx_year));

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
           coalesce(p.place,'') || ' ' || coalesce(p.region,'') || ' ' ||
           coalesce(p.country,'') ilike '%' || q_place || '%')
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
