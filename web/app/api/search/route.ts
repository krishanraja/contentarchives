import { NextRequest, NextResponse } from "next/server";
import { search } from "@/lib/data";

export async function GET(req: NextRequest) {
  const q = (req.nextUrl.searchParams.get("q") || "").slice(0, 200);
  const offset = Math.max(0, Number(req.nextUrl.searchParams.get("offset") || 0));
  return NextResponse.json(await search(q, offset));
}
