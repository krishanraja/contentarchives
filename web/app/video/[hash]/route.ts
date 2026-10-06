import { NextRequest, NextResponse } from "next/server";
import { playable } from "@/lib/data";
import { mediaRange } from "@/lib/drive";
import { getObject } from "@/lib/media";
import { imageSource } from "@/lib/env";

// A family video, streamed from Drive a piece at a time (Krish, 2026-10-06:
// "We also need videos to actually be able to play in the app"). Only a video
// judged whole and clear is ever streamed (migration 0009); any other answers
// 404, exactly like a photograph nobody may see.
//
// A phone's player asks for byte ranges and accepts a shorter piece than it
// asked for, then asks for the next. Every answer is at most CHUNK bytes, so
// no response comes near the hosting platform's size limit and a long video
// starts as fast as a short one.
const CHUNK = 3.5 * 1024 * 1024;
const CACHE = "private, max-age=86400";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest, ctx: { params: Promise<{ hash: string }> }) {
  const { hash } = await ctx.params;
  const v = await playable(hash);
  if (!v) return new NextResponse("not found", { status: 404 });
  const m = /^bytes=(\d+)-(\d*)$/.exec((req.headers.get("range") || "bytes=0-").trim());
  if (!m) return new NextResponse("only byte ranges from a start", { status: 416 });
  const from = Number(m[1]);
  const asked = m[2] ? Number(m[2]) : Infinity;
  if (asked < from) return new NextResponse("an empty range", { status: 416 });
  const to = Math.min(asked, from + CHUNK - 1);
  const base = { "content-type": v.mime, "accept-ranges": "bytes", "cache-control": CACHE };

  if (imageSource() === "fixture") {
    const buf = await getObject(`fixtures/${v.drive_id}.mp4`);
    if (!buf) return new NextResponse("not available", { status: 404 });
    if (from >= buf.length) {
      return new NextResponse(null, { status: 416, headers: { "content-range": `bytes */${buf.length}` } });
    }
    const end = Math.min(to, buf.length - 1);
    return new NextResponse(new Uint8Array(buf.subarray(from, end + 1)), { status: 206, headers: {
      ...base, "content-range": `bytes ${from}-${end}/${buf.length}`, "content-length": String(end - from + 1) } });
  }

  const r = await mediaRange(v.drive_id, from, to);
  if (r.status === 416) {
    return new NextResponse(null, { status: 416, headers: { "content-range": r.headers.get("content-range") || "bytes */*" } });
  }
  if (r.status !== 206 || !r.body) return new NextResponse("not available", { status: 502 });
  const headers: Record<string, string> = { ...base, "content-range": r.headers.get("content-range") || "" };
  const len = r.headers.get("content-length");
  if (len) headers["content-length"] = len;
  return new NextResponse(r.body, { status: 206, headers });
}
