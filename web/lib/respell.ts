import { sql } from "./db";
import { close, distance, fold } from "./spelling";

// Putting right a name already saved two ways (Krish, 2026-10-21: a child's
// name saved with one letter wrong, "How do we handle accidental
// misspellings?"). Saving never
// merges a near miss on its own (spelling.ts: Asha and Isha may be two people),
// so the owner is shown each pair of known names one slip apart and decides:
// the same person, kept under one spelling, or two people. Migration 0018 has
// the whole rule; the fix is written as answers, never as edits.

// The owner is the person signed in under ACCESS_ADMIN_EMAIL. A session holds
// a name, not an address, so the owner is the name on that address's row - and
// only while no one else let in carries the same name: two people called the
// same would both be refused, never both let in.
export async function ownerName(): Promise<string | null> {
  const admin = (process.env.ACCESS_ADMIN_EMAIL || "").trim().toLowerCase();
  if (!admin) return null;
  const rows = await sql()`select lower(o.name) who,
      (select count(*)::int from access_people x where lower(x.name) = lower(o.name) and x.status = 'yes') n
    from access_people o where o.email = ${admin} and o.status = 'yes'`;
  return rows.length && rows[0].n === 1 ? (rows[0].who as string) : null;
}

export async function isOwner(who: string | null): Promise<boolean> {
  return !!who && who === (await ownerName());
}

export type Side = { name: string; n: number; cover: string | null; others: number };
export type Pair = { a: Side; b: Side };

// The two keys of a pair, the smaller first (spelling_verdicts' primary key)
export function keys(a: string, b: string): [string, string] {
  const x = fold(a), y = fold(b);
  return x < y ? [x, y] : [y, x];
}

// Every pair of known names the "Did you mean ...?" rule would put to someone,
// that the owner has not decided yet, closest spelling first.
export function nearPairs(people: { name: string; n: number }[], decided: Set<string>): [string, string][] {
  const names = people.map((p) => p.name);
  const out: { a: string; b: string; d: number; n: number }[] = [];
  const seen = new Set<string>();
  const count = new Map(people.map((p) => [p.name, p.n]));
  for (const a of names) {
    for (const b of close(a, names.filter((x) => x !== a), 5)) {
      const k = keys(a, b).join("|");
      if (seen.has(k) || decided.has(k)) continue;
      seen.add(k);
      out.push({ a, b, d: distance(fold(a), fold(b)), n: (count.get(a) || 0) + (count.get(b) || 0) });
    }
  }
  return out.sort((x, y) => x.d - y.d || y.n - x.n).map((p) => [p.a, p.b]);
}

// The next pair to look at, and how many are left after it.
export async function nextPair(owner: string): Promise<{ pair: Pair | null; left: number }> {
  const db = sql();
  const [people, done, votes] = await Promise.all([
    db`select name, photo_count n, cover_face cover from people order by photo_count desc, name`,
    db`select a_key, b_key from spelling_verdicts`,
    // votes by someone other than the owner: his fix cannot change those
    db`select k, count(*)::int n from group_votes where field = 'person' and who <> ${owner} group by k`,
  ]);
  const decided = new Set(done.map((r) => `${r.a_key}|${r.b_key}`));
  const pairs = nearPairs(people.map((r) => ({ name: r.name as string, n: r.n as number })), decided);
  if (!pairs.length) return { pair: null, left: 0 };
  const others = new Map(votes.map((r) => [r.k as string, r.n as number]));
  const side = (name: string): Side => {
    const r = people.find((x) => x.name === name)!;
    return { name, n: r.n as number, cover: (r.cover as string) || null, others: others.get(fold(name)) || 0 };
  };
  const [a, b] = pairs[0];
  return { pair: { a: side(a), b: side(b) }, left: pairs.length - 1 };
}

// Both names are still known names, and one slip apart: a form posted by hand
// cannot rename anyone to anything.
export async function stillPair(a: string, b: string): Promise<boolean> {
  if (!a || !b || fold(a) === fold(b)) return false;
  const rows = await sql()`select name from people where name = ${a} or name = ${b}`;
  return rows.length === 2 && close(a, [b], 1).length === 1;
}

const CHUNK = 200;   // the most photographs one answer covers (saveAnswer's cap)

// The same person, kept as `right`: every face group named `wrong` gets the
// owner's answer `right`, and every photograph the library lists under `wrong`
// gets "not wrong, right". Returns how many photographs now say `right`.
export async function respell(owner: string, wrong: string, right: string): Promise<{ groups: number; photos: number }> {
  const db = sql();
  const [a_key, b_key] = keys(wrong, right);
  const out = await db.begin(async (tx) => {
    const groups = await tx`
      select distinct on (g.group_id) g.group_id, c.cluster_id
      from group_names g join clusters c on c.group_id = g.group_id
      where name_key(g.name) = name_key(${wrong})
      order by g.group_id, c.n desc, c.cluster_id`;
    for (const g of groups) {
      await tx`insert into answers (id, who, scope, target, field, value)
        values (gen_random_uuid(), ${owner}, 'cluster', ${g.cluster_id}, 'person', ${right})`;
    }
    const listed = (await tx`select hash from photos p
      where exists (select 1 from unnest(p.people) x where name_key(x) = name_key(${wrong}))
      order by hash`).map((r) => r.hash as string);
    for (let i = 0; i < listed.length; i += CHUNK) {
      const hashes = listed.slice(i, i + CHUNK);
      await tx`insert into answers (id, who, scope, target, field, value, hashes) values
        (gen_random_uuid(), ${owner}, 'file', ${hashes[0]}, 'not_in_photo', ${wrong}, ${hashes}::text[]),
        (gen_random_uuid(), ${owner}, 'file', ${hashes[0]}, 'in_photo', ${right}, ${hashes}::text[])`;
    }
    await tx`insert into spelling_verdicts (a_key, b_key, verdict, kept, who)
      values (${a_key}, ${b_key}, 'same', ${right}, ${owner})
      on conflict (a_key, b_key) do update set verdict = 'same', kept = excluded.kept, who = excluded.who, at = now()`;
    return { groups: groups.length, listed: listed.length };
  });
  // the kept list of who is in each photograph, then the names on Find; the
  // nightly run rebuilds `people` and the game's suggestions from the answers
  await db`select refresh_photo_people()`;
  const [n] = await db`select count(distinct hash)::int n from photo_people_mv pp
    join photos p using (hash) where p.visible and name_key(pp.name) = name_key(${right})`;
  await db.begin(async (tx) => {
    const [kept] = await tx`select name from people where name = ${right}`;
    if (kept) await tx`delete from people where name = ${wrong}`;
    else await tx`update people set name = ${right} where name = ${wrong}`;
    await tx`update people set photo_count = ${n.n} where name = ${right}`;
  });
  return { groups: out.groups, photos: n.n };
}

// Two people after all: only remembered, so the pair is not asked again.
export async function different(owner: string, a: string, b: string): Promise<void> {
  const [a_key, b_key] = keys(a, b);
  await sql()`insert into spelling_verdicts (a_key, b_key, verdict, kept, who)
    values (${a_key}, ${b_key}, 'different', null, ${owner})
    on conflict (a_key, b_key) do update set verdict = 'different', kept = null, who = excluded.who, at = now()`;
}
