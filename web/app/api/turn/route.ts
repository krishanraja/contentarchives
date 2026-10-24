import { NextRequest, NextResponse } from "next/server";
import { turnPhoto } from "@/lib/data";
import { me } from "@/lib/me";

// "Turn" on a photo's screen: a quarter clockwise ("right") or back ("left"),
// for everyone at once. The worker reads the photo's faces again the right way
// up on its next run.
export async function POST(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const { hash, way } = await req.json().catch(() => ({ hash: "", way: "" }));
  if (!/^[\w:.-]{8,80}$/.test(String(hash)) || (way !== "right" && way !== "left")) {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  const turn = await turnPhoto(who, String(hash), way === "right" ? 90 : -90);
  if (turn === null) return NextResponse.json({ ok: false }, { status: 404 });
  return NextResponse.json({ ok: true, turn });
}
