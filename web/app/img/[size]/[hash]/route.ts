import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { photoBytes, SIZES, type Size } from "@/lib/media";

const CACHE = "private, max-age=31536000, immutable";

export async function GET(_: NextRequest, ctx: { params: Promise<{ size: string; hash: string }> }) {
  const { size, hash } = await ctx.params;
  if (!(size in SIZES)) return new NextResponse("no such size", { status: 404 });
  const [p] = await sql()`select drive_id, media, visible from photos where hash = ${hash}`;
  if (!p || !p.visible) return new NextResponse("not found", { status: 404 });
  const bytes = await photoBytes(p.drive_id, p.media, size as Size);
  if (!bytes) return new NextResponse("not available", { status: 404 });
  return new NextResponse(new Uint8Array(bytes), {
    headers: { "content-type": "image/jpeg", "cache-control": CACHE },
  });
}
