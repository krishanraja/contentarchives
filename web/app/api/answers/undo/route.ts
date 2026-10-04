import { NextRequest, NextResponse } from "next/server";
import { undoAnswer } from "@/lib/data";
import { me } from "@/lib/me";

export async function POST(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const { id } = await req.json().catch(() => ({ id: "" }));
  return NextResponse.json({ ok: await undoAnswer(who, String(id || "")) });
}
