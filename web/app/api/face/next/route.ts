import { NextRequest, NextResponse } from "next/server";
import { nextFace } from "@/lib/data";
import { me } from "@/lib/me";

export async function GET(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const after = (req.nextUrl.searchParams.get("after") || "").split(",").filter(Boolean).slice(0, 50);
  return NextResponse.json(await nextFace(who, after));
}
