import sharp from "sharp";

// A square around a face, with context - the same 35% padding as
// people_sheet.crop(), because "a little context around the box reads far
// better than a tight crop". bbox is x1,y1,x2,y2 as FRACTIONS of the image the
// face was measured on, so it fits any size of the same picture.
export async function faceCrop(img: Buffer, bbox: number[], px = 240): Promise<Buffer> {
  const base = sharp(img).rotate();
  const { width = 1, height = 1 } = await base.metadata();
  const [x1, y1, x2, y2] = bbox.map(Number);
  const cx = ((x1 + x2) / 2) * width, cy = ((y1 + y2) / 2) * height;
  const side = Math.max((x2 - x1) * width, (y2 - y1) * height) * 1.7;
  const s = Math.max(12, Math.min(side, width, height));
  const left = Math.round(Math.min(Math.max(0, cx - s / 2), width - s));
  const top = Math.round(Math.min(Math.max(0, cy - s / 2), height - s));
  return sharp(img).rotate()
    .extract({ left, top, width: Math.round(s), height: Math.round(s) })
    .resize(px, px).jpeg({ quality: 82 }).toBuffer();
}
