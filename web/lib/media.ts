import { promises as fs } from "node:fs";
import path from "node:path";
import sharp from "sharp";
import { imageSource } from "./env";
import { download, thumbnail } from "./drive";
import { sql } from "./db";

// Private object storage: Supabase Storage in production, a folder in tests.
// It holds only derived bytes - video face frames from the seed and resized
// copies of Drive images - so losing it costs a re-fetch, never a photograph.
const LOCAL = path.join(process.cwd(), "fixtures", "media");

function supa() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  return url && key ? { url, key } : null;
}

export async function getObject(key: string): Promise<Buffer | null> {
  const s = supa();
  if (!s || imageSource() === "fixture") {
    try { return await fs.readFile(path.join(LOCAL, key)); } catch { return null; }
  }
  const r = await fetch(`${s.url}/storage/v1/object/media/${key}`, {
    headers: { authorization: `Bearer ${s.key}`, apikey: s.key },
  });
  return r.ok ? Buffer.from(await r.arrayBuffer()) : null;
}

// A video face's own frame: stored only after the library's sensitivity pass
// cleared THAT frame (stages/13_app/cloud_enrich.py frames(), migration 0005).
export async function frameBytes(key: string): Promise<Buffer | null> {
  const [r] = await sql()`select jpeg from frames where key = ${key} and status = 'ok'`;
  return r?.jpeg ? Buffer.from(r.jpeg as Uint8Array) : null;
}

export async function putObject(key: string, body: Buffer): Promise<void> {
  const s = supa();
  if (!s || imageSource() === "fixture") {
    const p = path.join(LOCAL, key);
    await fs.mkdir(path.dirname(p), { recursive: true });
    await fs.writeFile(p, body);
    return;
  }
  await fetch(`${s.url}/storage/v1/object/media/${key}`, {
    method: "POST",
    headers: { authorization: `Bearer ${s.key}`, apikey: s.key,
               "content-type": "image/jpeg", "x-upsert": "true" },
    body: new Uint8Array(body),
  });
}

export async function deletePrefix(keys: string[]): Promise<void> {
  const s = supa();
  if (!s || imageSource() === "fixture" || keys.length === 0) return;
  await fetch(`${s.url}/storage/v1/object/media`, {
    method: "DELETE",
    headers: { authorization: `Bearer ${s.key}`, apikey: s.key,
               "content-type": "application/json" },
    body: JSON.stringify({ prefixes: keys }),
  });
}

export const SIZES = { t: 480, v: 1600 } as const;
export type Size = keyof typeof SIZES;

async function fit(buf: Buffer, px: number): Promise<Buffer> {
  return sharp(buf).rotate().resize(px, px, { fit: "inside", withoutEnlargement: true })
    .jpeg({ quality: 80, mozjpeg: true }).toBuffer();
}

// The bytes for one photograph at one size. Cached under its Drive id, so a
// file replaced on Drive (a new id) is never served stale.
export async function photoBytes(driveId: string, media: string, size: Size): Promise<Buffer | null> {
  const key = `cache/${size}/${driveId}.jpg`;
  const hit = await getObject(key);
  if (hit) return hit;
  let src: Buffer | null = null;
  if (imageSource() === "fixture") {
    src = await getObject(`fixtures/${driveId}.jpg`);
  } else {
    src = await thumbnail(driveId, SIZES[size]).catch(() => null);
    if (!src && media === "photo") src = await download(driveId).catch(() => null);
  }
  if (!src) return null;
  const out = await fit(src, SIZES[size]);
  await putObject(key, out).catch(() => undefined);
  return out;
}
