-- archives.krishraja.com - the family app's index. DERIVED and disposable:
-- the library machine's journal (answers.csv) and Google Drive are the
-- sources of truth. One table is not derived: `answers`, which is the system
-- of record for what relatives say in the app until it is pulled into the
-- journal, and is therefore insert-only and never updated by the app except
-- for its own status column.
--
-- Nothing here is readable by the anon or authenticated roles. RLS is on for
-- every table with NO policies; only the Next.js server (service role) reads.

create extension if not exists vector;

-- Photographs and videos in the share set (stages/13_app/share_set.py), and
-- cloud-discovered Drive files once they pass the same rules.
create table photos (
  hash         text primary key,          -- blake2b-256 of the bytes; 'drive:<id>' until a cloud file is hashed
  drive_id     text unique,
  rel_path     text,                       -- under ContentLibrary, '/' separated
  md5          text,
  media        text not null default 'photo' check (media in ('photo','video')),
  taken_at     timestamptz,
  year         int,
  approx_year  text,                       -- a relative's "1980s", never mixed with year
  place        text,
  region       text,
  country      text,
  description  text,
  objects      text,
  activity     text,
  occasion     text,
  mood         text,
  people       text[] not null default '{}',
  day_key      text,                       -- photographs from one run of time (build_events), for "label the whole day"
  width        int,
  height       int,
  embedding    vector(768),
  source       text not null default 'seed' check (source in ('seed','cloud')),
  hidden       boolean not null default false,    -- "Hide this photo": out for everyone at once
  hidden_by    text,
  hidden_at    timestamptz,
  updated_at   timestamptz not null default now(),
  fts tsvector generated always as (
    to_tsvector('simple',
      coalesce(description,'') || ' ' || coalesce(place,'') || ' ' ||
      coalesce(region,'') || ' ' || coalesce(country,'') || ' ' ||
      coalesce(occasion,'') || ' ' || coalesce(activity,'') || ' ' ||
      coalesce(objects,'') || ' ' || coalesce(year::text,''))
  ) stored
);
create index photos_fts on photos using gin (fts);
create index photos_year on photos (year);
create index photos_day on photos (day_key);
create index photos_people on photos using gin (people);

-- Cloud files waiting on, or refused by, the sensitivity check. Never shown.
create table held (
  drive_id   text primary key,
  rel_path   text,
  reason     text not null,
  at         timestamptz not null default now()
);

create table clusters (
  cluster_id text primary key,
  group_id   text not null,
  name       text                          -- the journal's name at the last seed
);
create index clusters_group on clusters (group_id);

create table cluster_hashes (
  cluster_id text not null,
  group_id   text not null,
  hash       text not null references photos(hash) on delete cascade,
  primary key (cluster_id, hash)
);
create index cluster_hashes_group on cluster_hashes (group_id);
create index cluster_hashes_hash on cluster_hashes (hash);

create table faces (
  key        text primary key,             -- hash:image:face_index, the key verify_people_sheet checks
  hash       text not null references photos(hash) on delete cascade,
  group_id   text not null,
  bbox       real[] not null,              -- x1,y1,x2,y2 as FRACTIONS of the image it was measured on
  only_face  boolean not null default false,
  frame      text,                         -- storage path of a video frame, when the face is from video
  score      real
);
create index faces_group on faces (group_id);

-- The family set only: people who appear in Communal (resolve_audience).
create table people (
  name        text primary key,
  cover_face  text references faces(key) on delete set null,
  photo_count int not null default 0
);

create table queue (
  group_id     text primary key,
  rank         int not null,
  photo_count  int not null,
  hero_face    text not null references faces(key) on delete cascade,
  sample_faces text[] not null default '{}',
  suggestions  jsonb not null default '[]'  -- [{name, face, score}], family names only
);

create table players (
  name text primary key,
  sort int not null default 0
);

-- THE ONE TABLE THAT IS NOT DERIVED. id is generated ON THE PHONE, so a retry
-- after a dropped connection is the same row, never a second one.
create table answers (
  id         uuid primary key,
  at         timestamptz not null default now(),
  client_at  timestamptz,
  who        text not null,
  scope      text not null check (scope in ('cluster','file')),
  target     text not null,
  field      text not null,
  value      text not null check (char_length(value) between 1 and 60),
  hashes     text[] not null default '{}',
  status     text not null default 'new'
             check (status in ('new','undone','ingested','refused')),
  reason     text,
  check (
    (scope = 'cluster' and field in ('person','unidentifiable')) or
    (scope = 'file' and field in ('place','approx_year'))
  )
);
create index answers_target on answers (scope, target, at);
create index answers_status on answers (status);

-- "I don't know" belongs to one player: it must not decline a face for all.
create table skips (
  who      text not null,
  group_id text not null,
  at       timestamptz not null default now(),
  primary key (who, group_id)
);

create table gate_attempts (
  id      bigserial primary key,
  ip_hash text not null,
  ok      boolean not null,
  at      timestamptz not null default now()
);
create index gate_attempts_at on gate_attempts (at);

-- Every seed and every Drive sync writes one row. `watermark` is the newest
-- answer the seed's journal already contained: answers after it overlay the
-- seeded names, answers before it are already in them.
create table snapshots (
  id         bigserial primary key,
  at         timestamptz not null default now(),
  kind       text not null check (kind in ('seed','drive-sync')),
  counts     jsonb not null default '{}',
  head       text,
  watermark  timestamptz
);

create table sync_state (
  key   text primary key,
  value text not null
);

-- Names as the family sees them right now: the latest live app answer for a
-- group since the last seed, else the seeded name.
create view group_names as
with wm as (
  select coalesce(max(watermark), 'epoch'::timestamptz) as t
  from snapshots where kind = 'seed'
), latest as (
  select distinct on (target) target as group_id, field, value
  from answers, wm
  where scope = 'cluster' and status in ('new','ingested') and at > wm.t
  order by target, at desc
)
select c.group_id,
       case when l.field = 'person' then l.value
            when l.field is not null then null
            else max(c.name) end as name
from clusters c left join latest l on l.group_id = c.group_id
group by c.group_id, l.field, l.value;

create view photo_people as
select p.hash, unnest(p.people) as name from photos p
union
select ch.hash, g.name from cluster_hashes ch
join group_names g on g.group_id = ch.group_id
where g.name is not null;

-- Search: optional people / place / year filters, ranked by meaning when an
-- embedding is given, else by full text, else newest first.
create or replace function search_photos(
  q_embedding vector(768) default null,
  q_text      text default null,
  q_people    text[] default null,
  q_place     text default null,
  q_year_from int default null,
  q_year_to   int default null,
  q_limit     int default 60,
  q_offset    int default 0
) returns table (hash text, score real, total bigint)
language sql stable as $$
  with base as (
    select p.* from photos p
    where not p.hidden
      and (q_people is null or not exists (
            select 1 from unnest(q_people) want
            where not exists (select 1 from photo_people pp
                              where pp.hash = p.hash
                                and lower(pp.name) = lower(want))))
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

-- Lock everything down.
do $$
declare t text;
begin
  foreach t in array array['photos','held','clusters','cluster_hashes','faces',
    'people','queue','players','answers','skips','gate_attempts','snapshots',
    'sync_state'] loop
    execute format('alter table %I enable row level security', t);
    execute format('revoke all on %I from anon, authenticated', t);
  end loop;
end $$;
revoke all on group_names, photo_people from anon, authenticated;
revoke execute on function search_photos from anon, authenticated, public;

-- Private bucket for video face frames (Drive has one thumbnail per video)
-- and the lazily cached view-size images.
insert into storage.buckets (id, name, public) values ('media', 'media', false)
on conflict (id) do nothing;
