// The app's icon, at every size a browser or phone asks for, from one drawing:
//   npx tsx scripts/make-icons.ts
// A white instant photo, tilted, with a heart in it, on the app's sun-yellow
// tile: the same ink outline and hard "pop" shadow as every button
// (app/globals.css). At tab size detail is noise, so 16-48 px use a plainer
// cut - frame and heart only, heavier lines - drawn from the same shapes.
import { promises as fs } from "node:fs";
import path from "node:path";
import sharp from "sharp";

const INK = "#1e1433", SUN = "#ffc93c", PINK = "#ff9ccf", TOMATO = "#ff6a45", PAPER = "#ffffff";
const HEART = "M0 38 C-46 8 -60 -14 -60 -32 C-60 -52 -44 -64 -28 -64 C-14 -64 -4 -56 0 -46 C4 -56 14 -64 28 -64 C44 -64 60 -52 60 -32 C60 -14 46 8 0 38 Z";

// the photo, in a 512 box; `small` drops the shadow and the window, thickens the lines
function photo(small: boolean): string {
  const w = small ? 28 : 20;
  return `<g transform="rotate(-8 256 256)">
    ${small ? "" : `<rect x="138" y="118" width="280" height="320" rx="18" fill="${INK}"/>`}
    <rect x="116" y="96" width="280" height="320" rx="18" fill="${PAPER}" stroke="${INK}" stroke-width="${w}"/>
    ${small ? "" : `<rect x="148" y="128" width="216" height="196" rx="8" fill="${PINK}" stroke="${INK}" stroke-width="12"/>`}
    <path d="${HEART}" transform="translate(256 ${small ? 250 : 238}) scale(${small ? 1.45 : 1.15})" fill="${TOMATO}" stroke="${INK}" stroke-width="${small ? 18 : 12}" stroke-linejoin="round"/>
  </g>`;
}

// tile: the rounded yellow tile with an ink edge, for tabs and bookmarks.
// bleed: yellow to every edge, the photo shrunk into the middle, for phones
// that cut their own shape (iOS rounds it; Android may cut a circle).
function svg(kind: "tile" | "small" | "bleed", inner = 0.8): string {
  const art = kind === "bleed"
    ? `<rect width="512" height="512" fill="${SUN}"/><g transform="translate(256 256) scale(${inner}) translate(-256 -256)">${photo(false)}</g>`
    : `<rect x="12" y="12" width="488" height="488" rx="112" fill="${SUN}" stroke="${INK}" stroke-width="${kind === "small" ? 28 : 20}"/>${photo(kind === "small")}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">${art}</svg>`;
}

const png = (s: string, px: number) => sharp(Buffer.from(s), { density: Math.max(72, (72 * px) / 512 * 4) })
  .resize(px, px).png().toBuffer();

// An .ico may hold PNGs as they are: a 6-byte header, a 16-byte entry each, then the images.
function ico(images: { px: number; data: Buffer }[]): Buffer {
  const head = Buffer.alloc(6 + 16 * images.length);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(images.length, 4);
  let offset = head.length;
  images.forEach(({ px, data }, i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(px >= 256 ? 0 : px, e); head.writeUInt8(px >= 256 ? 0 : px, e + 1);
    head.writeUInt16LE(1, e + 4); head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(data.length, e + 8); head.writeUInt32LE(offset, e + 12);
    offset += data.length;
  });
  return Buffer.concat([head, ...images.map((i) => i.data)]);
}

async function main() {
  const root = path.join(__dirname, "..");
  const out = (p: string) => path.join(root, p);
  await fs.writeFile(out("app/icon.svg"), svg("tile"));
  const small = await Promise.all([16, 32, 48].map(async (px) => ({ px, data: await png(svg("small"), px) })));
  await fs.writeFile(out("app/favicon.ico"), ico(small));
  // iOS: no transparency, it rounds the corners itself
  await fs.writeFile(out("app/apple-icon.png"), await sharp(await png(svg("bleed", 1), 180)).flatten({ background: SUN }).png().toBuffer());
  await fs.writeFile(out("public/icon-192.png"), await png(svg("tile"), 192));
  await fs.writeFile(out("public/icon-512.png"), await png(svg("tile"), 512));
  // maskable: everything that matters inside the middle 80%
  await fs.writeFile(out("public/icon-maskable-512.png"), await png(svg("bleed", 0.8), 512));
  console.log("icons written");
}

void main();
