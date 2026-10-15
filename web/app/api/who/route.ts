import { NextRequest, NextResponse } from "next/server";
import { COOKIE, ME, cookieOptions, sign, signMe, verify } from "@/lib/session";

export async function POST(req: NextRequest) {
  const form = !(req.headers.get("content-type") || "").includes("application/json");
  const s = await verify(req.cookies.get(COOKIE)?.value);
  if (!s) {
    if (form) return NextResponse.redirect(new URL("/gate", req.url), 303);
    return new NextResponse("sign in first", { status: 401 });
  }
  // a plain form post when a name is tapped before the page's script arrives
  const { name } = form
    ? { name: String((await req.formData().catch(() => null))?.get("name") || "") }
    : await req.json().catch(() => ({ name: "" }));
  const who = String(name || "").normalize("NFKC").trim().replace(/\s+/g, " ").slice(0, 40);
  if (who.length < 2) {
    if (form) return NextResponse.redirect(new URL("/who?change", req.url), 303);
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  const res = form ? NextResponse.redirect(new URL("/", req.url), 303) : NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, await sign(who.toLowerCase(), s.via), cookieOptions());   // still the way it signed in
  // and this phone remembers them, past the next time the code is typed
  res.cookies.set(ME, await signMe(who.toLowerCase()), cookieOptions());
  return res;
}
