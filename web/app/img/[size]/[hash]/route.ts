import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { photoBytes, SIZES, type Size } from "@/lib/media";

// A photo can be turned the right way up after a phone has it (migration
// 0021), so a phone keeps it for ten minutes and then asks again: the answer
// is "nothing has changed" (304) unless the file or its turn has.
const CACHE = "private, max-age=600";

export async function GET(req: NextRequest, ctx: { params: Promise<{ size: string; hash: string }> }) {
  const { size, hash } = await ctx.params;
  if (!(size in SIZES)) return new NextResponse("no such size", { status: 404 });
  const [p] = await sql()`select drive_id, media, visible, turn from photos where hash = ${hash}`;
  if (!p || !p.visible) return new NextResponse("not found", { status: 404 });
  const tag = `"${p.drive_id}-${p.turn}"`;
  if (req.headers.get("if-none-match") === tag) return new NextResponse(null, { status: 304, headers: { etag: tag, "cache-control": CACHE } });
  const bytes = await photoBytes(p.drive_id, p.media, size as Size, p.turn as number);
  if (!bytes) return new NextResponse("not available", { status: 404 });
  return new NextResponse(new Uint8Array(bytes), {
    headers: { "content-type": "image/jpeg", "cache-control": CACHE, etag: tag },
  });
}
