import { NextRequest, NextResponse } from "next/server";
import { nextStory } from "@/lib/data";
import { me } from "@/lib/me";

export async function GET(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const after = (req.nextUrl.searchParams.get("after") || "").split(",").filter(Boolean).slice(0, 50);
  const only = req.nextUrl.searchParams.get("photo");
  return NextResponse.json(await nextStory(who, after, only));
}
