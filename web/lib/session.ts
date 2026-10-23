import { SignJWT, jwtVerify } from "jose";

export const COOKIE = "arch";
// A year from the last visit, for everyone who signs in by email (Krish,
// 2026-10-15: "for all new people"): middleware.ts signs such a session again
// once it is a day old, so a phone used even once a year is never asked again,
// and only one left untouched for a whole year signs out. A session from the
// retired family code carries no "via" and keeps the end it was given.
export const MAX_AGE = 365 * 24 * 3600;
export const REFRESH_AFTER = 24 * 3600;

export type Session = { v: string; who?: string; via?: string; iat: number };

function key(): Uint8Array {
  const s = process.env.SESSION_SECRET;
  if (!s || s.length < 16) throw new Error("SESSION_SECRET missing or short");
  return new TextEncoder().encode(s);
}
const version = () => process.env.SESSION_VERSION || "1";

// Every token this app signs carries exactly one of these claims, and each
// reader demands its own, so no kind of token can stand in for another: the
// "asking" cookie a stranger is handed is never a session, and never a
// sign-in link.
async function mint(claims: Record<string, string>, seconds: number): Promise<string> {
  return new SignJWT(claims)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + seconds)
    .sign(key());
}
async function read(token: string | undefined) {
  if (!token) return null;
  try {
    return (await jwtVerify(token, key(), { algorithms: ["HS256"] })).payload;
  } catch {
    return null;
  }
}

export async function sign(who?: string, via?: string): Promise<string> {
  return mint({ v: version(), ...(who ? { who } : {}), ...(via ? { via } : {}) }, MAX_AGE);
}

// null for absent, forged, expired, or signed under an older SESSION_VERSION
// (bumping it signs everyone out).
export async function verify(token: string | undefined): Promise<Session | null> {
  const p = await read(token);
  if (!p || p.v !== version()) return null;
  return { v: String(p.v), who: p.who ? String(p.who) : undefined, via: p.via ? String(p.via) : undefined,
    iat: Number(p.iat) || 0 };
}

// An emailed-code session signed more than a day ago is signed again on the next visit.
export function stale(s: Session, now = Math.floor(Date.now() / 1000)): boolean {
  return s.via === "email" && now - s.iat > REFRESH_AFTER;
}

// Who this device belongs to, kept apart from the session: a person's name is
// known once per phone, and signing in again (a lost or expired session, a
// SESSION_VERSION bump) finds it again. It is a name, not a key: it opens
// nothing on its own, so a version bump does not clear it. "Not you?" on the
// home screen replaces it.
export const ME = "arch_me";

export async function signMe(who: string): Promise<string> {
  return mint({ me: who }, MAX_AGE);
}

// The remembered name, or null. A session token is never mistaken for one
// (it carries no "me"), nor this for a session (it carries no "v").
export async function verifyMe(token: string | undefined): Promise<string | null> {
  const p = await read(token);
  return p && typeof p.me === "string" && p.me.length >= 2 ? p.me : null;
}

// The email a phone is signing in with, between typing it and typing the
// emailed code. It opens
// nothing: it only lets the sign-in screen carry on where it left off.
export const ASKING = "arch_ask";
export const ASKING_AGE = 30 * 24 * 3600;

export async function signAsking(email: string): Promise<string> {
  return mint({ pend: email }, ASKING_AGE);
}
export async function verifyAsking(token: string | undefined): Promise<string | null> {
  const p = await read(token);
  return p && typeof p.pend === "string" ? p.pend : null;
}

// The link in a sign-in email: it carries the address and that email's code,
// and runs out with the code. Opening it only shows a button; the tap posts
// the code like one typed, so a mail scanner opening it spends nothing.
export async function signLink(email: string, code: string, seconds: number): Promise<string> {
  return mint({ link: email, c: code }, seconds);
}
export async function verifyLink(token: string | undefined): Promise<{ email: string; code: string } | null> {
  const p = await read(token);
  return p && typeof p.link === "string" && typeof p.c === "string" ? { email: p.link, code: p.c } : null;
}

export function cookieOptions(maxAge = MAX_AGE) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}
