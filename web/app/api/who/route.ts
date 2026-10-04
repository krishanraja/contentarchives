import { NextRequest, NextResponse } from "next/server";
import { COOKIE, cookieOptions, sign, verify } from "@/lib/session";

export async function POST(req: NextRequest) {
  if (!(await verify(req.cookies.get(COOKIE)?.value))) {
    return new NextResponse("sign in first", { status: 401 });
  }
  const { name } = await req.json().catch(() => ({ name: "" }));
  const who = String(name || "").normalize("NFKC").trim().replace(/\s+/g, " ").slice(0, 40);
  if (who.length < 2) return NextResponse.json({ ok: false }, { status: 400 });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, await sign(who.toLowerCase()), cookieOptions());
  return res;
}
