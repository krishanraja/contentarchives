import { NextRequest, NextResponse } from "next/server";
import { hidePhoto } from "@/lib/data";
import { me } from "@/lib/me";

// Anyone can hide a photo for everyone, at once. Only Krish can bring it back
// (in the database), because a photo that should not be here must disappear
// before anyone has to argue about it.
export async function POST(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const { hash } = await req.json().catch(() => ({ hash: "" }));
  if (!/^[\w:.-]{8,80}$/.test(String(hash))) return NextResponse.json({ ok: false }, { status: 400 });
  await hidePhoto(who, String(hash));
  return NextResponse.json({ ok: true });
}
