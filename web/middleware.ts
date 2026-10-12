import { NextRequest, NextResponse } from "next/server";
import { COOKIE, ME, cookieOptions, sign, signMe, verify, verifyMe } from "@/lib/session";

// Every page, API and image is behind the family code. Only the gate itself,
// robots.txt, the app's icons (a phone fetches them without the cookie) and
// the build's own assets are not. The cron route checks its
// own secret instead.
const OPEN = [/^\/gate$/, /^\/api\/gate$/, /^\/robots\.txt$/, /^\/_next\//,
  /^\/favicon/, /^\/icon/, /^\/apple-icon/, /^\/api\/cron\//, /^\/manifest/];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  // Chrome offers /gate and /who back from history, since a first visit passes
  // through both: reopened by a phone that is already in, either one would ask
  // again for what it already knows. Home instead; only "Not you?" (/who?change)
  // opens the name screen for someone who has one.
  if (pathname === "/gate" || pathname === "/who") {
    const s = await verify(req.cookies.get(COOKIE)?.value);
    const named = s && (s.who || await verifyMe(req.cookies.get(ME)?.value));
    if (s && (pathname === "/gate" || (named && !req.nextUrl.searchParams.has("change")))) {
      return NextResponse.redirect(new URL("/", req.url));
    }
  }
  if (OPEN.some((re) => re.test(pathname))) return NextResponse.next();
  const s = await verify(req.cookies.get(COOKIE)?.value);
  const api = pathname.startsWith("/api/") || pathname.startsWith("/img/") || pathname.startsWith("/face/")
    || pathname.startsWith("/video/");
  if (!s) {
    if (api) return new NextResponse("sign in first", { status: 401 });
    return NextResponse.redirect(new URL("/gate", req.url));
  }
  if (!s.who && pathname !== "/who") {
    // the code is proved but the session has no name: if this phone said who
    // it is before, carry on as them rather than asking again
    const who = await verifyMe(req.cookies.get(ME)?.value);
    if (who) {
      const token = await sign(who);
      req.cookies.set(COOKIE, token);                 // this request already sees the name
      const res = NextResponse.next({ request: { headers: req.headers } });
      res.cookies.set(COOKIE, token, cookieOptions());
      return res;
    }
    if (!api) return NextResponse.redirect(new URL("/who", req.url));
  }
  // a phone that named itself before arch_me existed: remember it now, so the
  // next time the code is typed it is not asked its name again
  if (s.who && !req.cookies.get(ME)) {
    const res = NextResponse.next();
    res.cookies.set(ME, await signMe(s.who), cookieOptions());
    return res;
  }
  return NextResponse.next();
}

export const config = { matcher: "/:path*" };
