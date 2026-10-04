import { SignJWT, jwtVerify } from "jose";

export const COOKIE = "arch";
// 400 days is the longest a browser keeps a cookie. A grandparent types the
// code once.
export const MAX_AGE = 400 * 24 * 3600;

export type Session = { v: string; who?: string };

function key(): Uint8Array {
  const s = process.env.SESSION_SECRET;
  if (!s || s.length < 16) throw new Error("SESSION_SECRET missing or short");
  return new TextEncoder().encode(s);
}
const version = () => process.env.SESSION_VERSION || "1";

export async function sign(who?: string): Promise<string> {
  return new SignJWT({ v: version(), ...(who ? { who } : {}) })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + MAX_AGE)
    .sign(key());
}

// null for absent, forged, expired, or signed under an older SESSION_VERSION
// (bumping it signs everyone out).
export async function verify(token: string | undefined): Promise<Session | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, key(), { algorithms: ["HS256"] });
    if (payload.v !== version()) return null;
    return { v: String(payload.v), who: payload.who ? String(payload.who) : undefined };
  } catch {
    return null;
  }
}

export function cookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: MAX_AGE,
  };
}
