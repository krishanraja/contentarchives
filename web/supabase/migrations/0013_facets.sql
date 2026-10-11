-- Search that narrows from wherever it starts (Krish, 2026-10-11): "if someone
-- enters with a name, they should then be able to filter the time, content
-- type, location or say what they are actually looking for", and the same from
-- a place. And a video must be findable as a video.
--
-- 1. search_photos gains q_media ('photo' | 'video'). It is the LAST argument
--    and has a default, so the app's eight-argument call keeps working: this
--    migration can go live before the code that uses it.
-- 2. search_facets: for each of who / where / when / type, how many photos
--    each choice would give, counted against every OTHER filter in force. A
--    dimension's own filter is left out of its own counts, so a chosen year
--    still shows its neighbours and the family can switch, not only narrow.
--    Words never narrow the counts: they rank, they do not filter.
--    People are the one exception, because more than one can be chosen and
--    every one must be in the photo: the Who counts are "who ELSE is in
--    these", within the people already chosen. A chosen person is changed by
--    taking them off, not by tapping a neighbour.
--
-- photo_people is read ONCE per call (materialized): read per row it once
-- took over 60 s (0006); learning 80.

create index if not exists photos_media on photos (media) where not hidden and drive_id is not null;

-- The old eight-argument function is renamed aside, not dropped: this is
-- exactly what was applied to the live database on 2026-10-11 (its migration
-- tool held back a DROP), and leaving it under the old name would make an
-- eight-argument call ambiguous between the two.
alter function search_photos(extensions.vector, text, text[], text, int, int, int, int) rename to search_photos_0012;

create or replace function search_photos(
  q_embedding extensions.vector(768) default null,
  q_text      text default null,
  q_people    text[] default null,
  q_place     text default null,
  q_year_from int default null,
  q_year_to   int default null,
  q_limit     int default 60,
  q_offset    int default 0,
  q_media     text default null
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

revoke all on function search_photos(extensions.vector, text, text[], text, int, int, int, int, text) from anon, authenticated, public;

create or replace function search_facets(
  q_people    text[] default null,
  q_place     text default null,
  q_year_from int default null,
  q_year_to   int default null,
  q_media     text default null
) returns table (dim text, label text, n int, cover text)
language sql stable
set search_path = public
as $$
  with pp as materialized (
    select hash, name from photo_people where name is not null
  ), wanted as materialized (
    select pp.hash from pp
    where q_people is not null
      and lower(pp.name) in (select lower(w) from unnest(q_people) w)
    group by pp.hash
    having count(distinct lower(pp.name)) =
           (select count(distinct lower(w)) from unnest(q_people) w)
  ), shown as materialized (
    -- every visible photo, with each filter's answer worked out once
    select p.hash, p.media, p.when_year, coalesce(p.family_place, p.place) shown_place,
      (q_people is null or p.hash in (select w.hash from wanted w)) ok_people,
      (q_place is null or
       coalesce(p.family_place, coalesce(p.place,'') || ' ' || coalesce(p.region,'') || ' ' ||
       coalesce(p.country,'')) ilike '%' || q_place || '%') ok_place,
      ((q_year_from is null or p.when_year >= q_year_from)
       and (q_year_to is null or p.when_year <= q_year_to)) ok_year,
      (q_media is null or p.media = q_media) ok_media
    from photos p
    where not p.hidden and p.drive_id is not null
  ), people_counts as (
    select pp.name, count(distinct pp.hash)::int n
    from pp join shown s on s.hash = pp.hash
    where s.ok_people and s.ok_place and s.ok_year and s.ok_media
      and (q_people is null or lower(pp.name) not in (select lower(w) from unnest(q_people) w))
    group by pp.name order by n desc, pp.name limit 80
  )
  select 'media', s.media, count(*)::int, null::text
    from shown s where s.ok_people and s.ok_place and s.ok_year group by s.media
  union all
  select 'year', s.when_year::text, count(*)::int, null
    from shown s where s.ok_people and s.ok_place and s.ok_media and s.when_year is not null
    group by s.when_year
  union all
  (select 'place', s.shown_place, count(*)::int, null
    from shown s where s.ok_people and s.ok_year and s.ok_media and coalesce(s.shown_place, '') <> ''
    group by s.shown_place order by count(*) desc, s.shown_place limit 60)
  union all
  select 'person', c.name, c.n, (select pe.cover_face from people pe where pe.name = c.name)
    from people_counts c
$$;

revoke all on function search_facets(text[], text, int, int, text) from anon, authenticated, public;
