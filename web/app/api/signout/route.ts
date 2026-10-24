import { NextRequest, NextResponse } from "next/server";
import { ASKING, COOKIE, ME, cookieOptions } from "@/lib/session";

// "Sign out" in the top right of home (Krish, 2026-10-24): this phone forgets
// the session, whose phone it is, and any email it was part way through
// signing in with, so the next person starts at the sign-in screen. A plain
// form post, so it works before the page's script arrives; open to a phone
// already signed out, since all it does is clear.
export async function POST(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/gate", req.url), 303);
  for (const name of [COOKIE, ME, ASKING]) res.cookies.set(name, "", cookieOptions(0));
  return res;
}
