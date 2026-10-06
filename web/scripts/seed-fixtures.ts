// A synthetic family for building and testing the app: cartoon photographs,
// made-up people and places. NO real photograph or name is used anywhere in
// development - real faces live only on D: and Drive.
//
//   DATABASE_URL=... IMAGE_SOURCE=fixture npx tsx scripts/seed-fixtures.ts
import postgres from "postgres";
import sharp from "sharp";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";

const OUT = path.join(process.cwd(), "fixtures", "media", "fixtures");
const db = postgres(process.env.DATABASE_URL!, { prepare: false, max: 2 });

// [name, skin, hair, shirt]
const PEOPLE: [string, string, string, string][] = [
  ["Asha Raja", "#c98d5c", "#2b1a12", "#ff6a45"],
  ["Ravi Raja", "#a8693f", "#151010", "#7cc4ff"],
  ["Meera Shah", "#e0ac7e", "#5a3420", "#ff9ccf"],
  ["Dev Shah", "#8d5a37", "#0f0b0b", "#4fe0a5"],
  ["Priya Kapoor", "#d79f72", "#3b2216", "#b9a3ff"],
  ["Sam Kapoor", "#f1c6a0", "#a5652e", "#ffc93c"],
  // nobody has named these two yet: they are the "Who is this?" queue
  ["(stranger 1)", "#b97a4f", "#d9d9d9", "#2fb5a4"],
  ["(stranger 2)", "#e8b98f", "#1d1d1d", "#f4845f"],
];
const PLACES = ["Goa", "Brighton", "Delhi", "Lake District", "Mumbai", "Sydney", null];
const SCENES = [
  ["#7cc4ff", "#ffe08a", "at the beach, sand and sea behind them", "holiday", "playful"],
  ["#bde6a6", "#7bbf5f", "in a green garden on a sunny afternoon", "everyday", "candid"],
  ["#ffd1e8", "#ff9ccf", "at a birthday party with balloons and a cake", "birthday", "celebratory"],
  ["#ffe7b3", "#f2a541", "at a wedding with marigold garlands", "wedding", "celebratory"],
  ["#d8d2ff", "#9d8cff", "indoors in a living room, sitting on a sofa", "everyday", "quiet"],
  ["#c7f0ff", "#ffffff", "in the snow wearing warm coats", "holiday", "playful"],
] as const;

function face(cx: number, cy: number, r: number, p: [string, string, string, string]) {
  const [, skin, hair, shirt] = p;
  return `
    <ellipse cx="${cx}" cy="${cy + r * 2.3}" rx="${r * 1.5}" ry="${r * 1.2}" fill="${shirt}" stroke="#1e1433" stroke-width="${r * 0.08}"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="${skin}" stroke="#1e1433" stroke-width="${r * 0.08}"/>
    <path d="M${cx - r} ${cy - r * 0.15} Q${cx} ${cy - r * 1.6} ${cx + r} ${cy - r * 0.15} Q${cx} ${cy - r * 0.75} ${cx - r} ${cy - r * 0.15}Z" fill="${hair}"/>
    <circle cx="${cx - r * 0.35}" cy="${cy + r * 0.05}" r="${r * 0.1}" fill="#1e1433"/>
    <circle cx="${cx + r * 0.35}" cy="${cy + r * 0.05}" r="${r * 0.1}" fill="#1e1433"/>
    <path d="M${cx - r * 0.4} ${cy + r * 0.4} Q${cx} ${cy + r * 0.75} ${cx + r * 0.4} ${cy + r * 0.4}" fill="none" stroke="#1e1433" stroke-width="${r * 0.09}" stroke-linecap="round"/>`;
}

function rnd(seed: number) { const x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); }
const hex = (n: number) => n.toString(16).padStart(64, "0");

async function main() {
  await fs.mkdir(OUT, { recursive: true });
  await db`truncate photos, held, clusters, cluster_hashes, faces, people, queue, players,
           answers, skips, gate_attempts, snapshots, sync_state, video_checks cascade`;
  await db`insert into players ${db([{ name: "Grandma", sort: 1 }, { name: "Grandpa", sort: 2 }, { name: "Auntie Meera", sort: 3 }])}`;

  const W = 1200, H = 900;
  const photos: any[] = [], faces: any[] = [], ch: any[] = [];
  const clusterFaces = new Map<number, string[]>();
  for (let i = 0; i < 56; i++) {
    const sc = SCENES[i % SCENES.length];
    const n = 1 + Math.floor(rnd(i) * 3) % 3;
    const who = Array.from({ length: n }, (_, k) => Math.floor(rnd(i * 7 + k) * PEOPLE.length));
    const uniq = [...new Set(who)];
    let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
      <rect width="${W}" height="${H}" fill="${sc[0]}"/>
      <rect y="${H * 0.62}" width="${W}" height="${H * 0.38}" fill="${sc[1]}"/>
      <circle cx="${150 + rnd(i) * 900}" cy="${120 + rnd(i + 3) * 80}" r="${50 + rnd(i + 1) * 40}" fill="#fff6e9" opacity=".7"/>`;
    const hash = hex(i + 1);
    uniq.forEach((pIdx, k) => {
      const r = uniq.length === 1 ? 150 : 110;
      const cx = uniq.length === 1 ? 600 : 250 + k * (700 / Math.max(1, uniq.length - 1));
      const cy = 330 + rnd(i * 3 + k) * 60;
      svg += face(cx, cy, r, PEOPLE[pIdx]);
      const key = `${hash}::${k}`;
      faces.push({ key, hash, group_id: `g${pIdx + 1}`, cluster_id: `c${pIdx + 1}`, bbox: [(cx - r) / W, (cy - r * 1.3) / H, (cx + r) / W, (cy + r) / H],
                   only_face: uniq.length === 1, frame: null, score: 0.9 });
      ch.push({ cluster_id: `c${pIdx + 1}`, group_id: `g${pIdx + 1}`, hash });
      clusterFaces.set(pIdx, [...(clusterFaces.get(pIdx) || []), key]);
    });
    svg += "</svg>";
    await sharp(Buffer.from(svg)).jpeg({ quality: 85 }).toFile(path.join(OUT, `fx-${i + 1}.jpg`));
    const year = i % 9 === 4 ? null : 1984 + Math.floor(rnd(i + 11) * 40);
    const place = i % 5 === 2 ? null : PLACES[Math.floor(rnd(i + 5) * PLACES.length)];
    const named = uniq.filter((x) => x < 6).map((x) => PEOPLE[x][0]);
    photos.push({
      hash, drive_id: `fx-${i + 1}`, rel_path: `Media/Communal/${year ?? "NoDate"}/photo-${i + 1}.jpg`,
      md5: null, media: i % 13 === 7 ? "video" : "photo",
      taken_at: year ? new Date(Date.UTC(year, i % 12, 1 + (i % 27), 14)) : null,
      year, approx_year: null, place, region: null, country: null,
      description: `${uniq.length === 1 ? "One person" : `${uniq.length} people`} ${sc[2]}.`,
      objects: sc[2].split(" ").slice(-3).join(", "), activity: "posing for a photo",
      occasion: sc[3], mood: sc[4], people: named,
      day_key: year ? `${year}-${(i % 12) + 1}-${Math.floor(i / 4)}` : null,
      width: W, height: H, source: "seed",
    });
  }
  await db`insert into photos ${db(photos)}`;
  const clusters = PEOPLE.map((p, i) => ({ cluster_id: `c${i + 1}`, group_id: `g${i + 1}`, name: i < 6 ? p[0] : null,
    n: (clusterFaces.get(i) || []).length }));
  await db`insert into clusters ${db(clusters)}`;
  await db`insert into cluster_hashes ${db(ch)} on conflict do nothing`;
  await db`insert into faces ${db(faces)}`;
  await db`insert into people ${db(PEOPLE.slice(0, 6).map((p, i) => ({
    name: p[0], cover_face: (clusterFaces.get(i) || [])[0] || null,
    photo_count: (clusterFaces.get(i) || []).length })))}`;
  const queue = [6, 7].map((pIdx, rank) => {
    const keys = clusterFaces.get(pIdx) || [];
    const hero = faces.find((f) => keys.includes(f.key) && f.only_face)?.key || keys[0];
    return {
      group_id: `g${pIdx + 1}`, rank, photo_count: keys.length, hero_face: hero,
      sample_faces: keys.filter((k) => k !== hero).slice(0, 4),
      suggestions: (rank === 0
        ? [{ name: "Ravi Raja", face: (clusterFaces.get(1) || [])[0], score: 0.71 },
           { name: "Dev Shah", face: (clusterFaces.get(3) || [])[0], score: 0.52 }]
        : [{ name: "Meera Shah", face: (clusterFaces.get(2) || [])[0], score: 0.48 },
           { name: "Asha Raja", face: (clusterFaces.get(0) || [])[0], score: 0.44 }]),
    };
  }).filter((q) => q.hero_face);
  for (const q of queue) {
    await db`insert into queue (group_id, rank, photo_count, hero_face, sample_faces, suggestions)
      values (${q.group_id}, ${q.rank}, ${q.photo_count}, ${q.hero_face}, ${q.sample_faces}::text[], ${db.json(q.suggestions as any)})`;
  }
  // Videos (migration 0009): fx-8 plays - a test pattern judged clear, VP9 in
  // MP4 so the test browser (which has no H.264) plays it, and bigger than
  // one of the /video route's pieces so it is streamed in more than one;
  // fx-34 is in a format no phone plays; fx-21 is not judged yet.
  const vid = path.join(OUT, "fx-8.mp4");
  try {
    execFileSync("ffmpeg", ["-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=duration=8:size=1280x720:rate=24",
      "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "8M", "-pix_fmt", "yuv420p",
      "-movflags", "+faststart", vid]);
    await db`insert into video_checks (hash, status, mime, seconds, verdict) values (${hex(8)}, 'ok', 'video/mp4', 8, '[]'::jsonb)`;
  } catch { console.log("no ffmpeg here: the fixture video will not play"); }
  await db`insert into video_checks (hash, status, reason) values (${hex(34)}, 'unplayable', 'a format phones cannot play')`;
  await db`insert into snapshots (kind, counts, head, watermark) values ('seed', ${JSON.stringify({ photos: photos.length })}::jsonb, 'fixtures', now() - interval '1 day')`;
  console.log(`fixtures: ${photos.length} photos, ${faces.length} faces, ${queue.length} groups to name -> ${OUT}`);
  await db.end();
}
main().catch(async (e) => { console.error(e); await db.end(); process.exit(1); });
