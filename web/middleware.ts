import { NextRequest, NextResponse } from "next/server";
import { COOKIE, verify } from "@/lib/session";

// Every page, API and image is behind the family code. Only the gate itself,
// robots.txt and the build's own assets are not. The cron route checks its
// own secret instead.
const OPEN = [/^\/gate$/, /^\/api\/gate$/, /^\/robots\.txt$/, /^\/_next\//,
  /^\/favicon/, /^\/icon/, /^\/api\/cron\//, /^\/manifest/];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (OPEN.some((re) => re.test(pathname))) return NextResponse.next();
  const s = await verify(req.cookies.get(COOKIE)?.value);
  const api = pathname.startsWith("/api/") || pathname.startsWith("/img/") || pathname.startsWith("/face/");
  if (!s) {
    if (api) return new NextResponse("sign in first", { status: 401 });
    return NextResponse.redirect(new URL("/gate", req.url));
  }
  if (!s.who && !api && pathname !== "/who") {
    return NextResponse.redirect(new URL("/who", req.url));
  }
  return NextResponse.next();
}

export const config = { matcher: "/:path*" };
