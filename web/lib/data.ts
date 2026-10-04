import { sql } from "./db";
import { embed, hasGemini } from "./gemini";
import { describe, parseQuery } from "./search";

export type Card = {
  hash: string; media: string; year: number | null; approx_year: string | null;
  place: string | null; width: number | null; height: number | null;
};

export async function players(): Promise<string[]> {
  const rows = await sql()`select name from players order by sort, name`;
  return rows.map((r) => r.name as string);
}

export async function vocab() {
  const db = sql();
  const [people, places] = await Promise.all([
    db`select distinct name from photo_people where name is not null`,
    db`select place, count(*)::int n from photos
       where place is not null and place <> '' and not hidden
       group by place order by n desc limit 400`,
  ]);
  return { people: people.map((r) => r.name as string), places: places.map((r) => r.place as string) };
}

export async function search(q: string, offset = 0) {
  const { people, places } = await vocab();
  const p = parseQuery(q, people, places);
  let vec: number[] | null = null;
  let mode = "filters";
  if (p.rest && hasGemini()) {
    try { vec = await embed(p.rest); mode = "meaning"; } catch { mode = "words"; }
  } else if (p.rest) mode = "words";
  const db = sql();
  const rows = await db`
    select s.hash, s.score, s.total, ph.media, ph.year, ph.approx_year, ph.place,
           ph.width, ph.height
    from search_photos(
      ${vec ? `[${vec.join(",")}]` : null}::extensions.vector,
      ${!vec && p.rest ? p.rest : null},
      ${p.people.length ? p.people : null}::text[],
      ${p.place}, ${p.yearFrom}, ${p.yearTo}, 60, ${offset}) s
    join photos ph on ph.hash = s.hash`;
  const total = rows.length ? Number(rows[0].total) : 0;
  return {
    parsed: p, mode, total,
    sentence: describe(p, total),
    cards: rows.map((r) => ({
      hash: r.hash, media: r.media, year: r.year, approx_year: r.approx_year,
      place: r.place, width: r.width, height: r.height,
    })) as Card[],
  };
}

export async function browse() {
  const db = sql();
  const [people, places, years] = await Promise.all([
    db`select pp.name, count(distinct pp.hash)::int n,
              (select pe.cover_face from people pe where pe.name = pp.name) cover
       from photo_people pp join photos p on p.hash = pp.hash and not p.hidden
       group by pp.name order by n desc limit 60`,
    db`select place, count(*)::int n from photos
       where place is not null and place <> '' and not hidden
       group by place order by n desc limit 40`,
    db`select (coalesce(year, nullif(substring(approx_year from 1 for 4),'')::int) / 10 * 10) decade,
              count(*)::int n
       from photos where not hidden
         and coalesce(year, nullif(substring(approx_year from 1 for 4),'')::int) is not null
       group by 1 order by 1`,
  ]);
  return {
    people: people.map((r) => ({ name: r.name as string, n: r.n as number, cover: r.cover as string | null })),
    places: places.map((r) => ({ place: r.place as string, n: r.n as number })),
    decades: years.map((r) => ({ decade: r.decade as number, n: r.n as number })),
  };
}

export type PhotoRow = {
  hash: string; drive_id: string | null; media: string; taken_at: Date | null;
  year: number | null; approx_year: string | null; place: string | null;
  region: string | null; country: string | null; description: string | null;
  occasion: string | null; width: number | null; height: number | null; hidden: boolean;
};

export async function photo(hash: string): Promise<(PhotoRow & { people: string[] }) | null> {
  const db = sql();
  const [p] = await db<PhotoRow[]>`select hash, drive_id, media, taken_at, year, approx_year, place,
      region, country, description, occasion, width, height, hidden
    from photos where hash = ${hash}`;
  if (!p || p.hidden) return null;
  const who = await db`select distinct name from photo_people where hash = ${hash} order by name`;
  return { ...p, people: who.map((r) => r.name as string) };
}

export async function counts() {
  const db = sql();
  const [r] = await db`select
      (select count(*)::int from queue q where not exists (
         select 1 from group_names g where g.group_id = q.group_id and g.name is not null)
       and not exists (select 1 from answers a where a.scope = 'cluster'
         and a.target = q.group_id and a.status in ('new','ingested')
         and a.at > coalesce((select max(watermark) from snapshots where kind='seed'),'epoch'))) faces,
      (select count(*)::int from photos where not hidden and media = 'photo'
         and (place is null or (year is null and approx_year is null))) story,
      (select count(*)::int from photos where not hidden) photos`;
  return r as { faces: number; story: number; photos: number };
}

// ---------- the naming game ----------

export async function nextFace(who: string, after: string[] = []) {
  const db = sql();
  const [q] = await db`
    select q.* from queue q
    join faces f on f.key = q.hero_face
    join photos p on p.hash = f.hash and not p.hidden
    where not exists (select 1 from skips s where s.who = ${who} and s.group_id = q.group_id)
      and not exists (select 1 from answers a where a.scope = 'cluster'
            and a.target = q.group_id and a.status in ('new','ingested')
            and a.at > coalesce((select max(watermark) from snapshots where kind='seed'),'epoch'))
      and q.group_id <> all(${after}::text[])
    order by q.rank limit 1`;
  if (!q) return null;
  const keys = [q.hero_face, ...(q.sample_faces as string[])];
  const faces = await db`select f.key, f.hash, f.bbox, f.frame, f.only_face, p.media,
       p.width, p.height, p.place, p.year, p.approx_year
     from faces f join photos p on p.hash = f.hash
     where f.key = any(${keys}::text[]) and not p.hidden`;
  const byKey = new Map(faces.map((f) => [f.key as string, f]));
  const hero = byKey.get(q.hero_face);
  if (!hero) return null;
  // jsonb arrives parsed; a double-encoded string is tolerated, never trusted to be an array
  let raw: unknown = q.suggestions;
  if (typeof raw === "string") { try { raw = JSON.parse(raw); } catch { raw = []; } }
  const suggestions = (Array.isArray(raw) ? raw : []) as { name: string; face: string; score: number }[];
  return {
    group: q.group_id as string,
    photos: q.photo_count as number,
    hero,
    samples: (q.sample_faces as string[]).map((k) => byKey.get(k)).filter(Boolean),
    suggestions,
    // one strong suggestion becomes a yes/no question: "Is this Asha?"
    ask: suggestions[0] && suggestions[0].score >= 0.65 ? suggestions[0] : null,
  };
}

// ---------- where and when ----------

export async function nextStory(who: string, after: string[] = [], only: string | null = null) {
  const db = sql();
  // biggest day first: one answer about a 40-photo afternoon labels 40 photos
  const [p] = only ? await db`
    select p.hash, p.place, p.year, p.approx_year, p.day_key, p.width, p.height
    from photos p where p.hash = ${only} and not p.hidden and p.media = 'photo'` : await db`
    select p.hash, p.place, p.year, p.approx_year, p.day_key, p.width, p.height
    from photos p
    where not p.hidden and p.media = 'photo'
      and (p.place is null or (p.year is null and p.approx_year is null))
      and not exists (select 1 from skips s where s.who = ${who} and s.group_id = 'story:' || p.hash)
      and p.hash <> all(${after}::text[])
    order by (select count(*) from photos d where d.day_key = p.day_key) desc nulls last,
             p.hash
    limit 1`;
  if (!p) return null;
  const day = p.day_key ? await db`select hash from photos
      where day_key = ${p.day_key} and hash <> ${p.hash} and not hidden and place is null
      order by taken_at nulls last limit 40` : [];
  const places = await db`select place, count(*)::int n from photos
      where place is not null and place <> '' group by place order by n desc limit 8`;
  return {
    hash: p.hash as string, width: p.width, height: p.height,
    needPlace: !p.place, needYear: !p.year && !p.approx_year,
    day: day.map((r) => r.hash as string),
    places: places.map((r) => r.place as string),
  };
}

// ---------- answers: durable, idempotent, undoable ----------

export type AnswerIn = {
  id: string; kind: "person" | "mixed" | "place" | "year";
  group?: string; hashes?: string[]; value: string; client_at?: string;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const YEAR = /^(18[5-9]\d|19\d\d|20\d\d)s?$/;

export function validate(a: AnswerIn): string | null {
  if (!a || !UUID.test(a.id || "")) return "bad id";
  const v = (a.value || "").trim();
  if (!v || v.length > 60) return "a name or place is 1-60 letters";
  if (/^(\?+|for\s.+|-+)$/i.test(v)) return "that is a question, not an answer";
  if (a.kind === "person" || a.kind === "mixed") {
    if (!a.group) return "no face group";
  } else if (a.kind === "place" || a.kind === "year") {
    if (!a.hashes || !a.hashes.length || a.hashes.length > 200) return "no photos";
    if (a.kind === "year" && !YEAR.test(v)) return "a year is 1987 or a decade is 1980s";
  } else return "unknown answer";
  return null;
}

// Saves one answer. The id comes from the phone, so a retry after a dropped
// connection is the SAME row: never lost, never doubled. Returns how many
// photographs the answer now labels - the reward the screen shows.
export async function saveAnswer(who: string, a: AnswerIn): Promise<{ labelled: number }> {
  const db = sql();
  const value = a.value.trim().replace(/\s+/g, " ");
  return db.begin(async (tx) => {
    if (a.kind === "person" || a.kind === "mixed") {
      const [g] = await tx`select 1 from clusters where group_id = ${a.group!} limit 1`;
      if (!g) throw new Error("no such face group");
      await tx`insert into answers (id, client_at, who, scope, target, field, value)
        values (${a.id}, ${a.client_at || null}, ${who}, 'cluster', ${a.group!},
                ${a.kind === "person" ? "person" : "unidentifiable"},
                ${a.kind === "person" ? value : "mixed"})
        on conflict (id) do nothing`;
      const [n] = await tx`select count(distinct hash)::int n from cluster_hashes where group_id = ${a.group!}`;
      return { labelled: a.kind === "person" ? n.n : 0 };
    }
    // place / year: only photos the app is allowed to show
    const ok = await tx`select hash from photos where hash = any(${a.hashes!}::text[]) and not hidden`;
    const hashes = ok.map((r) => r.hash as string);
    if (!hashes.length) throw new Error("no such photographs");
    const field = a.kind === "place" ? "place" : "approx_year";
    const ins = await tx`insert into answers (id, client_at, who, scope, target, field, value, hashes)
      values (${a.id}, ${a.client_at || null}, ${who}, 'file', ${hashes[0]}, ${field}, ${value}, ${hashes}::text[])
      on conflict (id) do nothing returning id`;
    if (ins.length) {
      // shown at once; the journal pull and the next seed make it permanent
      if (field === "place")
        await tx`update photos set place = ${value}, updated_at = now()
                 where hash = any(${hashes}::text[]) and place is null`;
      else
        await tx`update photos set approx_year = ${value}, updated_at = now()
                 where hash = any(${hashes}::text[]) and year is null and approx_year is null`;
    }
    return { labelled: hashes.length };
  });
}

export const UNDO_MINUTES = 10;

// Undo within ten minutes. The pull never takes an answer younger than that,
// so an undone answer never reaches the journal.
export async function undoAnswer(who: string, id: string): Promise<boolean> {
  const db = sql();
  return db.begin(async (tx) => {
    const [a] = await tx`update answers set status = 'undone'
      where id = ${id} and who = ${who} and status = 'new'
        and at > now() - make_interval(mins => ${UNDO_MINUTES})
      returning scope, field, value, hashes`;
    if (!a) return false;
    if (a.scope === "file") {
      const col = a.field === "place" ? "place" : "approx_year";
      // put back only what this answer wrote, and only if no other live answer says the same
      await tx`update photos p set ${tx(col)} = null, updated_at = now()
        where p.hash = any(${a.hashes}::text[]) and ${tx(col)} = ${a.value}
          and not exists (select 1 from answers o where o.status in ('new','ingested')
            and o.field = ${a.field} and o.value = ${a.value} and p.hash = any(o.hashes))`;
    }
    return true;
  });
}

export async function skip(who: string, key: string) {
  await sql()`insert into skips (who, group_id) values (${who}, ${key}) on conflict do nothing`;
}

export async function hidePhoto(who: string, hash: string) {
  await sql()`update photos set hidden = true, hidden_by = ${who}, hidden_at = now() where hash = ${hash}`;
}
