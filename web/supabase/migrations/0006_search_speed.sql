-- 0006: a search by person finds the people's photographs ONCE.
--
-- Live, tapping a person (22,752 photos) timed out: the people filter asked
-- photo_people "is this person in THIS photo?" once per photograph, and
-- photo_people recomputes every group's name each time it is asked - over 60
-- seconds for one name. Asked once, the same view answers in about 0.2 s. The
-- photographs of everyone wanted (AND: all of them in the photo) are now
-- found first, and the filter is a lookup in that set. Same signature, same
-- rows, same order.

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
      and (q_year_from is null or coalesce(p.year,
             nullif(substring(p.approx_year from 1 for 4),'')::int) >= q_year_from)
      and (q_year_to is null or coalesce(p.year,
             nullif(substring(p.approx_year from 1 for 4),'')::int) <= q_year_to)
  ), ranked as (
    select b.hash,
      case
        when q_embedding is not null and b.embedding is not null
          then (1 - (b.embedding <=> q_embedding))::real
        when q_text is not null
          then ts_rank(b.fts, websearch_to_tsquery('simple', q_text))::real
        else 0::real
      end as score,
      b.taken_at
    from base b
    where q_embedding is not null
       or q_text is null
       or b.fts @@ websearch_to_tsquery('simple', q_text)
  )
  select r.hash, r.score, count(*) over () as total
  from ranked r
  order by
    case when q_embedding is null and q_text is null then 0 else -r.score end,
    r.taken_at desc nulls last
  limit q_limit offset q_offset
$$;

revoke all on function search_photos(extensions.vector, text, text[], text, int, int, int, int) from anon, authenticated, public;
