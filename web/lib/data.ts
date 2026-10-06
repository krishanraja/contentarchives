import type postgres from "postgres";
import { sql } from "./db";
import { embed, hasGemini } from "./gemini";
import { describe, parseQuery, type Parsed } from "./search";
import { exact } from "./spelling";

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
       where place is not null and place <> '' and visible
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
    sentence: describe(p, total, mode),
    cards: rows.map((r) => ({
      hash: r.hash, media: r.media, year: r.year, approx_year: r.approx_year,
      place: r.place, width: r.width, height: r.height,
    })) as Card[],
  };
}

// The second filter, after the first (Krish, 2026-10-06): tap a person, then
// narrow by year; tap a year, then narrow by person. Whatever the search has
// not chosen yet is offered as one row of chips. A meaning search ("at the
// beach") ranks every photo, so there is nothing to narrow and no row.
export type Refine =
  | { kind: "years"; active: string | null; items: { label: string; n: number }[] }
  | { kind: "people"; items: { name: string; n: number; cover: string | null }[] };

export async function refine(p: Parsed): Promise<Refine | null> {
  if (p.rest) return null;
  const db = sql();
  const yearOf = db`coalesce(ph.year, nullif(substring(ph.approx_year from 1 for 4), '')::int)`;
  const where = db`(${p.place}::text is null or
      coalesce(ph.place, '') || ' ' || coalesce(ph.region, '') || ' ' || coalesce(ph.country, '') ilike '%' || ${p.place} || '%')`;
  if (p.yearFrom !== null && !p.people.length) {
    // a year (or a decade) first: who is in these photos?
    const rows = await db`
      select pp.name, count(distinct pp.hash)::int n,
             (select pe.cover_face from people pe where pe.name = pp.name) cover
      from photo_people pp join photos ph on ph.hash = pp.hash and ph.visible
      where ${yearOf} between ${p.yearFrom} and ${p.yearTo} and ${where}
      group by pp.name order by n desc, pp.name limit 80`;
    return rows.length ? { kind: "people", items: rows.map((r) => ({ name: r.name as string, n: r.n as number, cover: r.cover as string | null })) } : null;
  }
  if (!p.people.length && !p.place) return null;
  // a person or a place first: which years? Many years are offered as their
  // decades first (a 15-year span would take seven "More" taps otherwise);
  // inside a decade, or beside a year already chosen, that decade's years.
  const decade = p.yearFrom !== null && p.yearFrom !== p.yearTo;
  const rows = await db`
    with wanted as materialized (
      select pp.hash from photo_people pp
      where ${p.people.length ? p.people : null}::text[] is not null
        and lower(pp.name) in (select lower(w) from unnest(${p.people.length ? p.people : null}::text[]) w)
      group by pp.hash
      having count(distinct lower(pp.name)) = ${p.people.length})
    select ${yearOf} y, count(*)::int n
    from photos ph
    where ph.visible and ${where}
      and (${p.people.length ? p.people : null}::text[] is null or ph.hash in (select hash from wanted))
    group by 1 having ${yearOf} is not null order by 1 desc`;
  const years = rows.map((r) => ({ y: Number(r.y), n: r.n as number }));
  const active = p.yearFrom === null ? null : decade ? `${p.yearFrom}s` : String(p.yearFrom);
  const within = p.yearFrom === null ? null : Math.floor(p.yearFrom / 10) * 10;
  let items: { label: string; n: number }[];
  if (within !== null) {
    items = years.filter((x) => x.y >= within && x.y <= within + 9).map((x) => ({ label: String(x.y), n: x.n }));
  } else if (years.length > 6 && new Set(years.map((x) => Math.floor(x.y / 10))).size > 1) {
    const by = new Map<number, number>();
    for (const x of years) by.set(Math.floor(x.y / 10) * 10, (by.get(Math.floor(x.y / 10) * 10) || 0) + x.n);
    items = [...by].sort((a, b) => b[0] - a[0]).map(([d, n]) => ({ label: `${d}s`, n }));
  } else {
    items = years.map((x) => ({ label: String(x.y), n: x.n }));
  }
  return items.length > 1 || active ? { kind: "years", active, items } : null;
}

// a search with one part changed, in the words the parser reads back
export function compose(p: Parsed, change: { people?: string[]; year?: string | null }): string {
  const people = change.people ?? p.people;
  const year = change.year !== undefined ? change.year
    : p.yearFrom === null ? null : p.yearFrom === p.yearTo ? String(p.yearFrom) : `${p.yearFrom}s`;
  return [...people, p.place, year].filter(Boolean).join(" ");
}

export async function browse() {
  const db = sql();
  const [people, places, years] = await Promise.all([
    db`select pp.name, count(distinct pp.hash)::int n,
              (select pe.cover_face from people pe where pe.name = pp.name) cover
       from photo_people pp join photos p on p.hash = pp.hash and p.visible
       group by pp.name order by n desc limit 200`,
    db`select place, count(*)::int n from photos
       where place is not null and place <> '' and visible
       group by place order by n desc limit 120`,
    db`select (coalesce(year, nullif(substring(approx_year from 1 for 4),'')::int) / 10 * 10) decade,
              count(*)::int n
       from photos where visible
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
  occasion: string | null; width: number | null; height: number | null; hidden: boolean; visible: boolean;
};

// play: a video judged whole and clear plays ('ok'); one in a format no phone
// plays keeps its still ('unplayable'); any other is not judged yet (null).
// Migration 0009.
export type Play = "ok" | "unplayable" | null;

export async function photo(hash: string): Promise<(PhotoRow & { people: string[]; play: Play }) | null> {
  const db = sql();
  const [p] = await db<(PhotoRow & { play: string | null })[]>`select p.hash, p.drive_id, p.media, p.taken_at, p.year,
      p.approx_year, p.place, p.region, p.country, p.description, p.occasion, p.width, p.height, p.hidden, p.visible,
      v.status as play
    from photos p left join video_checks v on v.hash = p.hash and p.media = 'video'
    where p.hash = ${hash}`;
  if (!p || !p.visible) return null;
  const who = await db`select distinct name from photo_people where hash = ${hash} order by name`;
  const play: Play = p.play === "ok" || p.play === "unplayable" ? p.play : null;
  return { ...p, play, people: who.map((r) => r.name as string) };
}

// The one video the /video route may stream: shown, a video, judged whole and clear.
export async function playable(hash: string): Promise<{ drive_id: string; mime: string } | null> {
  const [r] = await sql()`select p.drive_id, v.mime from photos p
    join video_checks v on v.hash = p.hash and v.status = 'ok'
    where p.hash = ${hash} and p.visible and p.media = 'video'`;
  return r ? { drive_id: r.drive_id as string, mime: r.mime as string } : null;
}

export async function counts() {
  const db = sql();
  const [r] = await db`select
      (select count(*)::int from queue q join group_names g on g.group_id = q.group_id
         where not g.answered) faces,
      (select count(*)::int from photos where visible and media = 'photo'
         and (place is null or (year is null and approx_year is null))) story,
      (select count(*)::int from photos where visible) photos`;
  return r as { faces: number; story: number; photos: number };
}

// ---------- the naming game ----------

// Which face to ask THIS person next (Krish, 2026-10-05: a skipped face must
// come back around, and nobody's answer overrides anybody else's):
//  - a face they have already answered is someone else's to answer now: their
//    one vote is in (migration 0007 counts it; nobody's replaces another's)
//  - "I don't know" moves a face to the back of THEIR queue for 30 days - it
//    comes back once they have seen the rest - and never out of anyone else's
//  - a face two or more people did not know goes behind the rest (it may be a
//    friend nobody in the family knows), still asked, never dropped
//  - otherwise the queue's own order: flagged and contested faces first
export async function nextFace(who: string, after: string[] = []) {
  const db = sql();
  const [q] = await db`
    with mine as (
      select distinct c.group_id from answers a join clusters c on c.cluster_id = a.target
      where a.who = ${who} and a.scope = 'cluster' and a.status in ('new', 'ingested')
        and a.field in ('person', 'unidentifiable')),
    shrugs as (
      select group_id, count(*) as n from skips where at > now() - interval '30 days' group by group_id)
    select q.*, f.cluster_id as hero_cluster, g.contested from queue q
    join faces f on f.key = q.hero_face
    join photos p on p.hash = f.hash and p.visible
    join group_names g on g.group_id = q.group_id
    left join skips s on s.who = ${who} and s.group_id = q.group_id and s.at > now() - interval '30 days'
    left join shrugs sh on sh.group_id = q.group_id
    where not g.answered
      and q.group_id not in (select group_id from mine)
      and q.group_id <> all(${after}::text[])
    order by (s.at is not null), s.at nulls first, coalesce(sh.n, 0) >= 2, q.rank
    limit 1`;
  if (!q) return null;
  // a tie: the answers in the running are offered to the next person
  const contest = q.contested
    ? (await db`select name from group_contest where group_id = ${q.group_id} order by n desc, name`).map((r) => r.name as string)
    : [];
  const keys = [q.hero_face, ...(q.sample_faces as string[])];
  const faces = await db`select f.key, f.hash, f.bbox, f.frame, f.only_face, p.media,
       p.width, p.height, p.place, p.year, p.approx_year
     from faces f join photos p on p.hash = f.hash
     where f.key = any(${keys}::text[]) and p.visible`;
  const byKey = new Map(faces.map((f) => [f.key as string, f]));
  const hero = byKey.get(q.hero_face);
  if (!hero) return null;
  // jsonb arrives parsed; a double-encoded string is tolerated, never trusted to be an array
  let raw: unknown = q.suggestions;
  if (typeof raw === "string") { try { raw = JSON.parse(raw); } catch { raw = []; } }
  const suggestions = (Array.isArray(raw) ? raw : []) as { name: string; face: string; score: number }[];
  return {
    group: q.group_id as string,
    cluster: (q.hero_cluster as string | null) || (q.group_id as string),
    photos: q.photo_count as number,
    hero,
    samples: (q.sample_faces as string[]).map((k) => byKey.get(k)).filter(Boolean),
    suggestions,
    contest,
    // one strong suggestion becomes a yes/no question: "Is this Asha?" - but not
    // on a contested face, where the choice between the answers given is the question
    ask: !contest.length && suggestions[0] && suggestions[0].score >= 0.65 ? suggestions[0] : null,
  };
}

// ---------- where and when ----------

export async function nextStory(who: string, after: string[] = [], only: string | null = null) {
  const db = sql();
  // biggest day first: one answer about a 40-photo afternoon labels 40 photos
  // A photo comes to this person while it still needs something THEY have not
  // answered; "I don't know" sends it to the back of their queue for 30 days.
  const [p] = only ? await db`
    select p.hash, p.place, p.year, p.approx_year, p.day_key, p.width, p.height
    from photos p where p.hash = ${only} and p.visible and p.media = 'photo'` : await db`
    with days as (select day_key, count(*) as n from photos where day_key is not null group by day_key)
    select p.hash, p.place, p.year, p.approx_year, p.day_key, p.width, p.height
    from photos p
    left join days d on d.day_key = p.day_key
    left join skips s on s.who = ${who} and s.group_id = 'story:' || p.hash and s.at > now() - interval '30 days'
    where p.visible and p.media = 'photo'
      and ((p.place is null and not exists (select 1 from answers a where a.who = ${who} and a.scope = 'file'
              and a.field = 'place' and a.status in ('new', 'ingested') and a.hashes @> array[p.hash]))
        or (p.year is null and p.approx_year is null and not exists (select 1 from answers a where a.who = ${who}
              and a.scope = 'file' and a.field = 'approx_year' and a.status in ('new', 'ingested') and a.hashes @> array[p.hash])))
      and p.hash <> all(${after}::text[])
    order by (s.at is not null), s.at nulls first, d.n desc nulls last, p.hash
    limit 1`;
  if (!p) return null;
  const day = p.day_key ? await db`select hash from photos
      where day_key = ${p.day_key} and hash <> ${p.hash} and visible and place is null
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
  group?: string; cluster?: string; hashes?: string[]; value: string; client_at?: string;
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
  let value = a.value.trim().replace(/\s+/g, " ");
  // a name or place that differs from a known one only in case, spacing or
  // punctuation IS that one, spelled the way the family already spells it
  if (a.kind === "person" || a.kind === "place") {
    const v = await vocab();
    value = exact(value, a.kind === "person" ? v.people : v.places) || value;
  }
  return db.begin(async (tx) => {
    if (a.kind === "person" || a.kind === "mixed") {
      // The answer names the CLUSTER the person was shown - frozen, never
      // renumbered - so a later merge of groups cannot detach it.
      const [c] = a.cluster
        ? await tx`select cluster_id from clusters where cluster_id = ${a.cluster} and group_id = ${a.group!}`
        : await tx`select cluster_id from clusters where group_id = ${a.group!} order by n desc, cluster_id limit 1`;
      if (!c) throw new Error("no such face group");
      await tx`insert into answers (id, client_at, who, scope, target, field, value)
        values (${a.id}, ${a.client_at || null}, ${who}, 'cluster', ${c.cluster_id},
                ${a.kind === "person" ? "person" : "unidentifiable"},
                ${a.kind === "person" ? value : "mixed"})
        on conflict (id) do nothing`;
      const [n] = await tx`select count(distinct hash)::int n from cluster_hashes where group_id = ${a.group!}`;
      return { labelled: a.kind === "person" ? n.n : 0 };
    }
    // place / year: only photos the app is allowed to show
    const ok = await tx`select hash from photos where hash = any(${a.hashes!}::text[]) and visible`;
    const hashes = ok.map((r) => r.hash as string);
    if (!hashes.length) throw new Error("no such photographs");
    const field = a.kind === "place" ? "place" : "approx_year";
    const ins = await tx`insert into answers (id, client_at, who, scope, target, field, value, hashes)
      values (${a.id}, ${a.client_at || null}, ${who}, 'file', ${hashes[0]}, ${field}, ${value}, ${hashes}::text[])
      on conflict (id) do nothing returning id`;
    if (ins.length) await settle(tx, field, hashes);
    return { labelled: hashes.length };
  });
}

// What a photo shows for a place or a year the FAMILY gave: each person's latest
// answer is one vote, the answer most people gave wins (a tie goes to the first
// given), spellings folded as in name_key. A second person's different answer
// is counted, never written over the first. A place or year the LIBRARY gave
// (no family answer matches it) is never replaced by an answer here.
type Tx = postgres.TransactionSql;
async function settle(tx: Tx, field: "place" | "approx_year", hashes: string[]) {
  const col = field;
  const familyOwned = tx`(p.${tx(col)} is null or exists (select 1 from answers o where o.scope = 'file'
      and o.field = ${field} and o.hashes @> array[p.hash] and name_key(o.value) = name_key(p.${tx(col)})))`;
  await tx`
    with v as (
      select distinct on (h, a.who) h, a.who, a.value, a.at
      from answers a cross join lateral unnest(a.hashes) h
      where a.scope = 'file' and a.field = ${field} and a.status in ('new', 'ingested')
        and a.hashes && ${hashes}::text[] and h = any(${hashes}::text[])
      order by h, a.who, a.at desc),
    s as (select h, name_key(value) as k, value, count(*) as c, min(at) as f from v group by h, name_key(value), value),
    t as (select h, k, sum(c) as n, min(f) as f from s group by h, k),
    w as (select distinct on (h) h, k from t order by h, n desc, f),
    sp as (select distinct on (h, k) h, k, value from s order by h, k, c desc, f)
    update photos p set ${tx(col)} = sp.value, updated_at = now()
    from w join sp on sp.h = w.h and sp.k = w.k
    where p.hash = w.h and p.${tx(col)} is distinct from sp.value and ${familyOwned}
      ${col === "approx_year" ? tx`and p.year is null` : tx``}`;
  // no live family answer left (all undone): a family value goes, a library one stays
  await tx`
    update photos p set ${tx(col)} = null, updated_at = now()
    where p.hash = any(${hashes}::text[]) and p.${tx(col)} is not null
      and exists (select 1 from answers o where o.scope = 'file' and o.field = ${field}
                  and o.hashes @> array[p.hash] and name_key(o.value) = name_key(p.${tx(col)}))
      and not exists (select 1 from answers o where o.scope = 'file' and o.field = ${field}
                  and o.status in ('new', 'ingested') and o.hashes @> array[p.hash])`;
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
    // the photo shows what everyone else's answers now add up to
    if (a.scope === "file") await settle(tx, a.field === "place" ? "place" : "approx_year", a.hashes as string[]);
    return true;
  });
}

export async function skip(who: string, key: string) {
  // a second "I don't know" sends it to the back of their queue again
  await sql()`insert into skips (who, group_id) values (${who}, ${key})
    on conflict (who, group_id) do update set at = now()`;
}

export async function hidePhoto(who: string, hash: string) {
  await sql()`update photos set hidden = true, hidden_by = ${who}, hidden_at = now() where hash = ${hash}`;
}
