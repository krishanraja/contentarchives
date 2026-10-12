-- 0014: Find narrows fast, and Where can be "in the UK" or "abroad".
--
-- Krish, 2026-10-12, on the Find screen after choosing a person: "If I go
-- into Rishi I can't then easily select an era or, say, for example, UK versus
-- abroad, which would be handy ... the whole thing is so slow and laggy."
--
-- 1. photo_people_mv: who is in each photograph, kept ready. photo_people is a
--    view that works out every face group's name from the answers each time
--    it is read (about 0.2 s), and both search functions read it on every
--    tap. The two search functions now read this copy instead. It is
--    refreshed by the nightly worker after grouping, and by the app straight
--    after any answer about who someone is (refresh_photo_people). Everything
--    else - the photo page, the owner's private rules, the Personal rule -
--    still reads the live view, so nothing about privacy waits on a refresh.
-- 2. place_country: the country a place name is in. A photograph's country
--    is the family's place, if they gave one and it is known; else the
--    camera's GPS country; else its library place name, looked up. Names are
--    matched by place_key (letters and digits only), so "Blue Lagoon Iceland"
--    and "Blue Lagoon, Iceland" are one place. The table holds no rows in
--    this file: they are family place names and live only in the database
--    (the repository is public). learn_place_countries() fills it from the
--    GPS photographs' own place and country; the rest were added by hand.
-- 3. search_photos and search_facets gain q_country: a country, or
--    'abroad' (any known country but the United Kingdom). It is the LAST
--    argument with a default, so the code already deployed keeps working;
--    the previous versions are renamed aside, not dropped (as in 0013).
--    The place filter now also matches by place_key, and search_facets
--    counts places by place_key (shown under their commonest spelling) and
--    adds a 'country' dimension.

create or replace function place_key(t text) returns text
language sql immutable parallel safe
as $$ select nullif(regexp_replace(lower(t), '[^[:alnum:]]+', '', 'g'), '') $$;   -- null for no name

create table if not exists place_country (
  place_key text primary key,
  country   text not null,
  source    text not null default 'hand',    -- 'gps' (learned) | 'hand'
  at        timestamptz not null default now()
);
alter table place_country enable row level security;
revoke all on place_country from anon, authenticated;

alter table photos add column if not exists family_place_key text generated always as (place_key(family_place)) stored;
alter table photos add column if not exists place_key text generated always as (place_key(place)) stored;

-- A place name seen on GPS photographs is in the country they were taken in
-- (the commonest, if more than one). Never overwrites a name added by hand.
create or replace function learn_place_countries() returns int
language sql
set search_path = public
as $$
  with seen as (
    select place_key(place) k, mode() within group (order by country) c
    from photos
    where coalesce(place, '') <> '' and coalesce(country, '') <> ''
    group by 1
  ), ins as (
    insert into place_country (place_key, country, source)
    select k, c, 'gps' from seen where k is not null
    on conflict (place_key) do update set country = excluded.country, at = now()
      where place_country.source = 'gps' and place_country.country <> excluded.country
    returning 1
  )
  select count(*)::int from ins
$$;
revoke all on function learn_place_countries() from anon, authenticated, public;
select learn_place_countries();

create materialized view if not exists photo_people_mv as
  select distinct hash, name from photo_people where name is not null;
create unique index if not exists photo_people_mv_key on photo_people_mv (hash, name);
create index if not exists photo_people_mv_lname on photo_people_mv (lower(name));
revoke all on photo_people_mv from anon, authenticated;

create or replace function refresh_photo_people() returns void
language sql
set search_path = public
as $$ refresh materialized view concurrently photo_people_mv $$;
revoke all on function refresh_photo_people() from anon, authenticated, public;

alter function search_photos(extensions.vector, text, text[], text, int, int, int, int, text) rename to search_photos_0013;
alter function search_facets(text[], text, int, int, text) rename to search_facets_0013;

create or replace function search_photos(
  q_embedding extensions.vector(768) default null,
  q_text      text default null,
  q_people    text[] default null,
  q_place     text default null,
  q_year_from int default null,
  q_year_to   int default null,
  q_limit     int default 60,
  q_offset    int default 0,
  q_media     text default null,
  q_country   text default null
) returns table (hash text, score real, total bigint)
language sql stable
set search_path = public, extensions
as $$
  with wanted as materialized (
    select pp.hash
    from photo_people_mv pp
    where q_people is not null
      and lower(pp.name) in (select lower(w) from unnest(q_people) w)
    group by pp.hash
    having count(distinct lower(pp.name)) =
           (select count(distinct lower(w)) from unnest(q_people) w)
  ), base as (
    select p.*,
      coalesce(fc.country, nullif(p.country, ''), lc.country) shown_country
    from photos p
    left join place_country fc on fc.place_key = p.family_place_key
    left join place_country lc on lc.place_key = p.place_key
    where not p.hidden and p.drive_id is not null
      and (q_people is null or p.hash in (select w.hash from wanted w))
      and (q_place is null
           or coalesce(p.family_place, coalesce(p.place,'') || ' ' || coalesce(p.region,'') || ' ' ||
              coalesce(p.country,'')) ilike '%' || q_place || '%'
           or (place_key(q_place) is not null and coalesce(p.family_place_key, p.place_key) like '%' || place_key(q_place) || '%'))
      and (q_year_from is null or p.when_year >= q_year_from)
      and (q_year_to is null or p.when_year <= q_year_to)
      and (q_media is null or p.media = q_media)
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
    where (q_country is null
           or (q_country = 'abroad' and b.shown_country is not null and b.shown_country <> 'United Kingdom')
           or b.shown_country = q_country)
      and (q_embedding is not null
           or q_text is null
           or b.fts @@ websearch_to_tsquery('simple', q_text))
  )
  select r.hash, r.score, count(*) over () as total
  from ranked r
  order by
    case when q_embedding is null and q_text is null then 0 else -r.score end,
    r.when_year desc nulls last, r.taken_at desc nulls last
  limit q_limit offset q_offset
$$;
revoke all on function search_photos(extensions.vector, text, text[], text, int, int, int, int, text, text) from anon, authenticated, public;

create or replace function search_facets(
  q_people    text[] default null,
  q_place     text default null,
  q_year_from int default null,
  q_year_to   int default null,
  q_media     text default null,
  q_country   text default null
) returns table (dim text, label text, n int, cover text)
language sql stable
set search_path = public
as $$
  with wanted as materialized (
    select pp.hash from photo_people_mv pp
    where q_people is not null
      and lower(pp.name) in (select lower(w) from unnest(q_people) w)
    group by pp.hash
    having count(distinct lower(pp.name)) =
           (select count(distinct lower(w)) from unnest(q_people) w)
  ), shown as materialized (
    -- every visible photo, with each filter's answer worked out once
    select p.hash, p.media, p.when_year,
      coalesce(p.family_place, p.place) shown_place,
      coalesce(p.family_place_key, p.place_key) shown_key,
      coalesce(fc.country, nullif(p.country, ''), lc.country) shown_country,
      (q_people is null or p.hash in (select w.hash from wanted w)) ok_people,
      (q_place is null
       or coalesce(p.family_place, coalesce(p.place,'') || ' ' || coalesce(p.region,'') || ' ' ||
          coalesce(p.country,'')) ilike '%' || q_place || '%'
       or (place_key(q_place) is not null and coalesce(p.family_place_key, p.place_key) like '%' || place_key(q_place) || '%')) ok_place,
      ((q_year_from is null or p.when_year >= q_year_from)
       and (q_year_to is null or p.when_year <= q_year_to)) ok_year,
      (q_media is null or p.media = q_media) ok_media
    from photos p
    left join place_country fc on fc.place_key = p.family_place_key
    left join place_country lc on lc.place_key = p.place_key
    where not p.hidden and p.drive_id is not null
  ), shown2 as materialized (
    select s.*, (q_country is null
       or (q_country = 'abroad' and s.shown_country is not null and s.shown_country <> 'United Kingdom')
       or s.shown_country = q_country) ok_country
    from shown s
  ), people_counts as (
    select pp.name, count(distinct pp.hash)::int n
    from photo_people_mv pp join shown2 s on s.hash = pp.hash
    where s.ok_people and s.ok_place and s.ok_year and s.ok_media and s.ok_country
      and (q_people is null or lower(pp.name) not in (select lower(w) from unnest(q_people) w))
    group by pp.name order by n desc, pp.name limit 80
  )
  select 'media', s.media, count(*)::int, null::text
    from shown2 s where s.ok_people and s.ok_place and s.ok_year and s.ok_country group by s.media
  union all
  select 'year', s.when_year::text, count(*)::int, null
    from shown2 s where s.ok_people and s.ok_place and s.ok_media and s.ok_country and s.when_year is not null
    group by s.when_year
  union all
  -- countries are counted without the place or country chosen, so the family can switch
  select 'country', s.shown_country, count(*)::int, null
    from shown2 s where s.ok_people and s.ok_year and s.ok_media and s.shown_country is not null
    group by s.shown_country
  union all
  (select 'place', mode() within group (order by s.shown_place), count(*)::int, null
    from shown2 s where s.ok_people and s.ok_year and s.ok_media and s.ok_country and s.shown_key is not null
    group by s.shown_key order by count(*) desc, 2 limit 60)
  union all
  select 'person', c.name, c.n, (select pe.cover_face from people pe where pe.name = c.name)
    from people_counts c
$$;
revoke all on function search_facets(text[], text, int, int, text, text) from anon, authenticated, public;
