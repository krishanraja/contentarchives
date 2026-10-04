import { NextRequest, NextResponse } from "next/server";
import { saveAnswer, validate, type AnswerIn } from "@/lib/data";
import { me } from "@/lib/me";

export async function POST(req: NextRequest) {
  const who = await me();
  if (!who) return new NextResponse("who are you?", { status: 401 });
  const a = (await req.json().catch(() => null)) as AnswerIn | null;
  const bad = validate(a as AnswerIn);
  if (bad) return NextResponse.json({ ok: false, error: bad }, { status: 400 });
  try {
    return NextResponse.json({ ok: true, ...(await saveAnswer(who, a!)) });
  } catch (e) {
    // 422: the phone must NOT retry this one - it can never succeed
    return NextResponse.json({ ok: false, error: (e as Error).message }, { status: 422 });
  }
}
