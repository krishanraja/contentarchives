import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { codeMatches, ipHash, lockState } from "@/lib/gate";
import { COOKIE, cookieOptions, sign } from "@/lib/session";
import { need } from "@/lib/env";

export async function POST(req: NextRequest) {
  const { code } = await req.json().catch(() => ({ code: "" }));
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "local";
  const ih = ipHash(ip, need("SESSION_SECRET"));
  const db = sql();
  const [c] = await db`select
      count(*) filter (where ip_hash = ${ih} and not ok)::int ip,
      count(*) filter (where not ok)::int total
    from gate_attempts where at > now() - interval '1 hour'`;
  const lock = lockState(c.ip, c.total);
  if (lock !== "ok") {
    return NextResponse.json({ ok: false, locked: true }, { status: 429 });
  }
  const ok = codeMatches(String(code || ""), need("ACCESS_CODE"));
  await db`insert into gate_attempts (ip_hash, ok) values (${ih}, ${ok})`;
  if (!ok) {
    if (lockState(c.ip, c.total + 1) === "global" && process.env.ALERT_WEBHOOK_URL) {
      await fetch(process.env.ALERT_WEBHOOK_URL, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: "archives.krishraja.com: the family code gate locked after too many wrong guesses" }),
      }).catch(() => undefined);
    }
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, await sign(), cookieOptions());
  return res;
}
