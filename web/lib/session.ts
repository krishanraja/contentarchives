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

// Who this device belongs to, kept apart from the family code's session: a
// person says their name once per phone, and re-entering the code (a lost or
// expired session, a SESSION_VERSION bump) finds it again. It is a name, not a
// key: it opens nothing without the code, so a version bump does not clear it.
// "Not you?" on the home screen replaces it.
export const ME = "arch_me";

export async function signMe(who: string): Promise<string> {
  return new SignJWT({ me: who })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + MAX_AGE)
    .sign(key());
}

// The remembered name, or null. A session token is never mistaken for one
// (it carries no "me"), nor this for a session (it carries no "v").
export async function verifyMe(token: string | undefined): Promise<string | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, key(), { algorithms: ["HS256"] });
    return typeof payload.me === "string" && payload.me.length >= 2 ? payload.me : null;
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
