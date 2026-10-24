import { describe, expect, it } from "vitest";
import sharp from "sharp";
import { norm, turnBox } from "../lib/turn";
import { faceCrop } from "../lib/crop";

describe("a photo turned the right way up (migration 0021)", () => {
  it("counts turns clockwise, whole quarters only", () => {
    expect([0, 90, 360, 450, -90, -180].map(norm)).toEqual([0, 90, 0, 90, 270, 180]);
  });

  it("turns a face box with its picture: a quarter clockwise, upside down, a quarter back", () => {
    // a face near the top-left corner of a picture
    const b = [0.1, 0.2, 0.3, 0.4];
    expect(turnBox(b, 0, 90).map((v) => +v.toFixed(5))).toEqual([0.6, 0.1, 0.8, 0.3]);    // now top right
    expect(turnBox(b, 0, 180).map((v) => +v.toFixed(5))).toEqual([0.7, 0.6, 0.9, 0.8]);   // bottom right
    expect(turnBox(b, 0, 270).map((v) => +v.toFixed(5))).toEqual([0.2, 0.7, 0.4, 0.9]);   // bottom left
    expect(turnBox(b, 90, 90)).toEqual(b);                                                // measured as shown
    expect(turnBox(turnBox(b, 0, 90), 90, 0).map((v) => +v.toFixed(5))).toEqual(b);       // and back again
  });

  it("the box lands on the same pixels sharp turns them to", async () => {
    // a 40x20 picture, black but for one white square near the top left
    const raw = Buffer.alloc(40 * 20 * 3);
    for (let y = 2; y < 6; y++) for (let x = 4; x < 8; x++) raw.fill(255, (y * 40 + x) * 3, (y * 40 + x) * 3 + 3);
    const img = await sharp(raw, { raw: { width: 40, height: 20, channels: 3 } }).png().toBuffer();
    const box = [4 / 40, 2 / 20, 8 / 40, 6 / 20];
    for (const t of [90, 180, 270]) {
      const turned = await sharp(img).rotate(t).png().toBuffer();
      const { width, height } = await sharp(turned).metadata();
      const [x1, y1, x2, y2] = turnBox(box, 0, t);
      const cx = Math.floor(((x1 + x2) / 2) * width!), cy = Math.floor(((y1 + y2) / 2) * height!);
      const { data } = await sharp(turned).extract({ left: cx, top: cy, width: 1, height: 1 }).raw().toBuffer({ resolveWithObject: true });
      expect(data[0]).toBeGreaterThan(200);
    }
  });

  it("a face is cut from the picture as shown, so a turned photo gives an upright face", async () => {
    const img = await sharp({ create: { width: 300, height: 200, channels: 3, background: "#888" } }).jpeg().toBuffer();
    const out = await faceCrop(await sharp(img).rotate(90).jpeg().toBuffer(), turnBox([0.1, 0.1, 0.3, 0.4], 0, 90), 60);
    expect((await sharp(out).metadata()).width).toBe(60);
  });
});
