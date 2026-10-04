import { NextRequest, NextResponse } from "next/server";
import { skip } from "@/lib/data";
import { me } from "@/lib/me";

export async function POST(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const { key } = await req.json().catch(() => ({ key: "" }));
  if (!/^(story:)?[\w:.-]{1,80}$/.test(String(key))) return NextResponse.json({ ok: false }, { status: 400 });
  await skip(who, String(key));
  return NextResponse.json({ ok: true });
}
