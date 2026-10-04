import { NextResponse } from "next/server";
import { vocab } from "@/lib/data";

export async function GET() {
  const v = await vocab();
  return NextResponse.json({ people: v.people.sort((a, b) => a.localeCompare(b)), places: v.places });
}
