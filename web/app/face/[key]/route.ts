import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { frameBytes, photoBytes } from "@/lib/media";
import { faceCrop } from "@/lib/crop";

export async function GET(req: NextRequest, ctx: { params: Promise<{ key: string }> }) {
  const key = decodeURIComponent((await ctx.params).key);
  const [f] = await sql()`select f.bbox, f.frame, p.drive_id, p.media, p.visible, p.source
    from faces f join photos p on p.hash = f.hash where f.key = ${key}`;
  // a face is drawn only on the picture its box was measured on. No box: the
  // library measured it on a video frame no one has judged for sensitivity, or
  // on a thumbnail that is gone. A library box on a video without its own judged
  // frame was measured on the library's frame grab, not the frame Drive shows.
  if (!f || !f.visible || !f.bbox) return new NextResponse("not found", { status: 404 });
  if (!f.frame && f.media === "video" && f.source === "seed") return new NextResponse("not found", { status: 404 });
  // a video face is drawn on its OWN judged frame (frames, status ok), never the video's thumbnail
  const img = f.frame ? await frameBytes(f.frame) : await photoBytes(f.drive_id, f.media, "v");
  if (!img) return new NextResponse("not available", { status: 404 });
  // ?whole=1: the picture the face is in (a video's frame, or the photo), for
  // the big "Who is this?" image with the ring drawn over it
  const out = req.nextUrl.searchParams.get("whole") ? img : await faceCrop(img, f.bbox as number[]);
  return new NextResponse(new Uint8Array(out), {
    headers: { "content-type": "image/jpeg", "cache-control": "private, max-age=31536000, immutable" },
  });
}
