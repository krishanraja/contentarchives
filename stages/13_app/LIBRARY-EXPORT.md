# The library export: the last time the app needs the library machine

Krish, 2026-10-05: "make it such that this is never reliant on a local machine or
external drive again". Everything the library learned about the Communal
photographs (descriptions, places, dates, faces, who is who, every answer the
family gave) lives in `library.db`, `_enrichment` and the answers journal on the
library machine's drives. Drive holds only the photographs. This export carries
that knowledge to the cloud ONCE. After the cloud imports it, Supabase is the
system of record and no step of the app reads a local drive again.

Two writers, one contract (this file):

- **The library machine** writes the export: `stages/13_app/export_library.py`
  (read-only on the library), into Google Drive through the local Drive client:
  `H:\My Drive\Archives-Library\archives-library.sqlite`. No credential is needed
  on the machine, and Drive keeps the file as a permanent archive copy.
- **The cloud** imports it: `stages/13_app/cloud_enrich.py` finds the file through
  the read-only service account (it is shared with that account and nothing
  else), binds every row to its Drive file by md5 (then by path), and then
  classifies only the files the library never described.

## Rules the export never breaks

1. **Communal only, by the library's own rule.** `photos` is exactly
   `share_set()`'s shared set: Communal, every rule, Krish's nudity rule
   included. Nothing from Personal, Archive, `_Review` or Intimate. Ever.
2. **Everything held out stays held out.** `held` lists every Communal file the
   share rules keep out, and every blocklisted (purged) hash whose md5 is known,
   so the cloud never classifies, shows or re-judges one of them. A purged file
   still sitting on Drive must arrive here as held.
3. **Joined by key, never by position** (learning 45): face embeddings join on
   (hash, face_index) for photographs and (image, face_index) for video frames;
   description vectors join on hash.
4. **Read-only on the library.** `library.db`, the journal and the media are
   opened read-only; nothing on D:, F: or H:\My Drive\ContentLibrary is written.
5. **The export never enters git.** It carries family names and face
   embeddings; the repository is public. It lives in Krish's Drive, shared with
   the service account only.
6. **Atomic.** Written to `archives-library.sqlite.partial`, verified, then
   renamed, so Drive never syncs half a file.

## Format 1 (SQLite)

```sql
create table meta (key text primary key, value text);
-- format = '1'; created_at (UTC ISO 8601); repo_head; counts (JSON of table -> rows).
-- No paths, no names in meta.

create table photos (
  hash        text primary key,      -- the library's blake2b-256, hex
  md5         text,                  -- of the file's bytes (h-mirror.csv): how the cloud finds it on Drive
  rel_path    text not null,         -- under ContentLibrary, '/'-separated: 'Media/Communal/2014/a.jpg'
  media       text not null,         -- 'photo' | 'video'
  taken_at    text, year int, approx_year text,
  place text, region text, country text,
  description text, objects text, activity text, occasion text, mood text,
  people      text not null default '[]',   -- JSON array of the family names on this file
  day_key     text,                  -- EVENTS.json event start: "label the whole day"
  width int, height int,
  embedding   blob                   -- 768 x float32 little-endian, unit length; NULL if none
);

create table held (
  hash text primary key, md5 text, rel_path text,
  reason text not null               -- a category word (e.g. 'nudity', 'screenshot', 'removed'), never a description
);

create table clusters (
  cluster_id text primary key,       -- the library's frozen cluster id, as the journal names it
  group_id   text not null           -- after CLUSTER-MERGES.csv: decided by people, kept by the cloud
);

create table faces (
  key        text primary key,       -- '{hash}:{image}:{face_index}', image '' for a photograph
  hash       text not null,          -- a photos.hash
  image      text not null default '',  -- the video frame key, '' for a photograph
  face_index int  not null,
  cluster_id text not null,          -- a clusters.cluster_id
  x1 real, y1 real, x2 real, y2 real,   -- FRACTIONS of the thumbnail the box was measured on; NULL for video faces
  thumb_w int, thumb_h int,          -- that thumbnail's size in pixels (the cloud checks orientation against Drive)
  det   real,                        -- detector score
  share real,                        -- min(box w, box h) / min(thumb w, thumb h), in pixels; NULL for video
  only_face int not null,            -- 1 if it is the only face in that image or frame
  embedding blob not null            -- 512 x float32 little-endian, unit length (buffalo_l w600k_r50)
);

create table answers (
  id     text primary key,           -- uuid5(NAMESPACE_URL, 'journal:' + when|who|scope|target|field|value)
  at     text not null,              -- the journal's 'when'
  who    text not null,
  scope  text not null,              -- 'cluster' | 'file'
  target text not null,              -- a clusters.cluster_id or a photos.hash
  field  text not null, value text not null,
  confidence real, note text
);
```

`answers` is every journal row (corrections included, oldest first) whose
target is an exported cluster or an exported hash, verbatim. The cloud keeps the
fields the app understands (`person`, `unidentifiable`, `place`, `approx_year`);
the rest are already folded into `photos` by `build_db`.

## What the cloud does with it (`cloud_enrich.py`)

- imports it once per distinct file (its md5 is recorded in `sync_state`), and
  stops the run if the file's tables disagree with its own `meta` counts;
- keeps everything it holds for good: `photos` and `faces` (with every box and
  embedding), `clusters` (pinned, with centroids), `library_held`, and the whole
  journal in `journal`;
- binds `photos` and `held` to Drive files **by md5**. By `rel_path` only for a
  row with no md5: a Drive file whose bytes differ from the library's under the
  same name is a different file (an edit, or a replacement), so it is judged
  afresh rather than inheriting the library's verdict. With md5 at 100% this
  costs a classification per changed file and nothing else;
- held wins every tie, now and later: a file matching `library_held` is held
  without being classified, shown or re-judged, including a purged file that
  turns up on Drive months from now;
- a library row replaces a cloud-classified row for the same Drive file; a
  second copy of a library photograph is held as `duplicate`;
- a library row whose Drive file leaves is unbound, not deleted, and re-binds
  when the file returns; until then no page shows it (`photos.visible`);
- keeps the library's groups: two library groups are never merged by the cloud,
  and cloud clusters may join them;
- imports the journal's cluster answers (`person`, `unidentifiable`,
  `needs_identifying`) into `answers` with status `ingested`, so names and
  verdicts flow through the same path as app answers. The last answer for a
  group decides, as in `build_game.verdicts`: `needs_identifying` ("ask someone
  else") keeps the face in the queue and asks it first;
- a face is drawn only when its box was measured on a picture the shape Drive
  shows. A library box on a video was measured on the library's own frame grab,
  so it is never drawn; box-less faces group and find people only;
- a video face (`image` = `{hash}_t{ms}`) the queue needs is given a frame of its
  own: the cloud pulls that one frame from the video on Drive, finds the same
  person in it by embedding, and shows it only if the library's sensitivity pass
  clears THAT frame (`frames`, migration 0005).
