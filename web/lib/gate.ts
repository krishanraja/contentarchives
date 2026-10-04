import { createHash, timingSafeEqual } from "node:crypto";

// Case and spaces never matter: "archives ", "Archives" and "ARCHIVES" are
// the same code to someone typing with one thumb.
export function normalise(code: string): string {
  return (code || "").normalize("NFKC").replace(/\s+/g, "").toUpperCase();
}

export function codeMatches(given: string, expected: string): boolean {
  if (!expected) return false;
  const a = createHash("sha256").update(normalise(given)).digest();
  const b = createHash("sha256").update(normalise(expected)).digest();
  return timingSafeEqual(a, b);
}

export const PER_IP_FAILURES = 10;   // in an hour, from one network
export const GLOBAL_FAILURES = 200;  // in an hour, from everywhere: someone is guessing

export type Lock = "ok" | "ip" | "global";
export function lockState(ipFailures: number, globalFailures: number): Lock {
  if (globalFailures >= GLOBAL_FAILURES) return "global";
  if (ipFailures >= PER_IP_FAILURES) return "ip";
  return "ok";
}

export function ipHash(ip: string, salt: string): string {
  return createHash("sha256").update(salt + "|" + ip).digest("hex").slice(0, 32);
}

// Links opened from WhatsApp, Instagram or Facebook open in their own browser,
// which keeps its own cookies - so the code would be asked for every time.
export function inAppBrowser(ua: string): boolean {
  return /(FBAN|FBAV|Instagram|WhatsApp|Line\/|; wv\)|GSA\/)/i.test(ua || "");
}
