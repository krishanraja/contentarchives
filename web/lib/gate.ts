import { createHash } from "node:crypto";

// Wrong codes, counted per network and in all: someone guessing is stopped.
// (Since 2026-10-15 the codes are the ones emailed to each person; the shared
// family code no longer lets anyone new in.)
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

export function clientIp(forwardedFor: string | null): string {
  return (forwardedFor || "").split(",")[0].trim() || "local";
}

// Links opened from WhatsApp, Instagram or Facebook open in their own browser,
// which keeps its own cookies - so the code would be asked for every time.
export function inAppBrowser(ua: string): boolean {
  return /(FBAN|FBAV|Instagram|WhatsApp|Line\/|; wv\)|GSA\/)/i.test(ua || "");
}
