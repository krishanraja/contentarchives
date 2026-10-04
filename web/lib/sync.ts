import type postgres from "postgres";
import type { DriveFile } from "./drive";
import { cloudHold, type Verdict } from "./share";

// The daily Drive sync: what keeps the app "always on" with no library
// machine. Idempotent - a second run with nothing new changes nothing.
//
//   1. BIND seeded rows to their Drive file, by md5 then by path
//   2. REMOVE rows whose Drive file is gone (a derived copy must not outlive
//      the original, learning 57) - but never on a listing that looks broken
//   3. ADD new Communal files: classify with the library's own prompts, apply
//      the SAME nudity rule as the seed, and show only what passes

export type Deps = {
  list: () => Promise<DriveFile[]>;
  image: (f: DriveFile) => Promise<Buffer | null>;
  classify: ((jpeg: Buffer) => Promise<Record<string, any>>) | null;   // null: no Gemini key
  embed: ((text: string) => Promise<number[]>) | null;
  budget: number;            // new files classified per run
  now?: () => number;
  deadline?: number;         // ms timestamp to stop adding by
};

export type Report = {
  listed: number; bound: number; removed: number; added: number; held: number;
  waiting: number; refusedRemoval: string | null; replaced: number; seeded: boolean;
};

const YEAR_DIR = /(?:^|\/)((?:18|19|20)\d\d)(?:\/|$)/;

export async function syncDrive(db: postgres.Sql, d: Deps): Promise<Report> {
  const files = await d.list();
  const r: Report = { listed: files.length, bound: 0, removed: 0, added: 0, held: 0, waiting: 0,
    refusedRemoval: null, replaced: 0, seeded: false };
  const byId = new Map(files.map((f) => [f.id, f]));

  // 1. bind
  const unbound = await db`select hash, md5, rel_path from photos where drive_id is null`;
  if (unbound.length) {
    const byMd5 = new Map(files.filter((f) => f.md5Checksum).map((f) => [f.md5Checksum!.toLowerCase(), f]));
    const byPath = new Map(files.map((f) => [f.relPath.toLowerCase(), f]));
    const holders = new Map((await db`select drive_id, source, hash from photos where drive_id is not null`)
      .map((x) => [x.drive_id as string, { source: x.source as string, hash: x.hash as string }]));
    for (const u of unbound) {
      const f = (u.md5 && byMd5.get(String(u.md5).toLowerCase())) || (u.rel_path && byPath.get(String(u.rel_path).toLowerCase()));
      if (!f) continue;
      const holder = holders.get(f.id);
      // A row the cloud described by itself gives way to the seed's row for
      // the same file: the seed carries faces, names and the library's
      // knowledge. A SEED row holding the file is never displaced.
      if (holder && holder.source !== "cloud") continue;
      if (holder) {
        await db`delete from photos where hash = ${holder.hash}`;
        r.replaced++;
      }
      await db`update photos set drive_id = ${f.id}, updated_at = now() where hash = ${u.hash}`;
      holders.set(f.id, { source: "seed", hash: u.hash });
      r.bound++;
    }
  }

  // 2. remove - unless the listing looks broken. An empty or collapsed
  // listing is far more likely a failed API call than a deleted family.
  const known = await db`select hash, drive_id from photos where drive_id is not null`;
  const gone = known.filter((k) => !byId.has(k.drive_id));
  if (known.length > 20 && gone.length > known.length * 0.2) {
    r.refusedRemoval = `${gone.length} of ${known.length} photos missing from Drive - refusing to remove any; a listing that broken is a failed call until proven otherwise`;
  } else if (gone.length) {
    await db`delete from photos where hash = any(${gone.map((g) => g.hash)}::text[])`;
    r.removed = gone.length;
  }
  await db`delete from held where drive_id <> all(${[...byId.keys()]}::text[])`;

  // 3. add
  const seen = new Set([
    ...(await db`select drive_id from photos where drive_id is not null`).map((x) => x.drive_id as string),
    ...(await db`select drive_id from held`).map((x) => x.drive_id as string),
  ]);
  const fresh = files.filter((f) => !seen.has(f.id));
  r.waiting = fresh.length;
  // NOTHING IS CLASSIFIED BEFORE THE FIRST SEED. Before it, every one of
  // ~24,000 Communal files looks "new": the cron would start describing the
  // whole library at Gemini's price, a few dozen a day, and every row it made
  // would duplicate one the seed is about to bring with faces and names.
  r.seeded = (await db`select 1 from snapshots where kind = 'seed' limit 1`).length > 0;
  if (!r.seeded || !d.classify) return r;    // they wait; nothing is shown unjudged
  const now = d.now || Date.now;
  for (const f of fresh.slice(0, d.budget)) {
    if (d.deadline && now() > d.deadline) break;
    const media = f.mimeType.startsWith("video/") ? "video" : "photo";
    const jpeg = await d.image(f).catch(() => null);
    if (!jpeg) continue;                     // retried next run
    let v: Record<string, any>;
    try { v = await d.classify(jpeg); } catch { continue; }
    const why = cloudHold(media, v as Verdict);
    if (why) {
      await db`insert into held (drive_id, rel_path, reason) values (${f.id}, ${f.relPath}, ${why})
               on conflict (drive_id) do update set reason = excluded.reason, at = now()`;
      r.held++;
    } else {
      const desc = String(v.description || "").slice(0, 1000) || null;
      let vec: number[] | null = null;
      if (desc && d.embed) vec = await d.embed(desc).catch(() => null);
      const y = f.relPath.match(YEAR_DIR);
      await db`insert into photos (hash, drive_id, rel_path, md5, media, year, place, description,
          objects, activity, occasion, mood, embedding, source)
        values (${"drive:" + f.id}, ${f.id}, ${f.relPath}, ${f.md5Checksum || null}, ${media},
          ${y ? Number(y[1]) : null}, ${v.place ? String(v.place).slice(0, 80) : null}, ${desc},
          ${v.objects || null}, ${v.activity || null}, ${v.occasion || null}, ${v.mood || null},
          ${vec ? `[${vec.join(",")}]` : null}::vector, 'cloud')
        on conflict (hash) do nothing`;
      r.added++;
    }
    r.waiting--;
  }
  await db`insert into snapshots (kind, counts) values ('drive-sync', ${db.json(r as any)})`;
  return r;
}
