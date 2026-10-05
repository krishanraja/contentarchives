import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { codeMatches, ipHash, lockState } from "@/lib/gate";
import { COOKIE, cookieOptions, sign } from "@/lib/session";
import { need } from "@/lib/env";

// A tap on "Open" before the page's script has arrived is a plain form post: it
// must still work, and answer with a page, not JSON. (A slow phone is the norm
// for the people this is for.)
const isForm = (req: NextRequest) => !(req.headers.get("content-type") || "").includes("application/json");
const back = (req: NextRequest, to: string) => NextResponse.redirect(new URL(to, req.url), 303);

export async function POST(req: NextRequest) {
  const form = isForm(req);
  const { code } = form
    ? { code: String((await req.formData().catch(() => null))?.get("code") || "") }
    : await req.json().catch(() => ({ code: "" }));
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "local";
  const ih = ipHash(ip, need("SESSION_SECRET"));
  const db = sql();
  const [c] = await db`select
      count(*) filter (where ip_hash = ${ih} and not ok)::int ip,
      count(*) filter (where not ok)::int total
    from gate_attempts where at > now() - interval '1 hour'`;
  const lock = lockState(c.ip, c.total);
  if (lock !== "ok") {
    if (form) return back(req, "/gate?e=locked");
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
    if (form) return back(req, "/gate?e=wrong");
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const res = form ? back(req, "/who") : NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, await sign(), cookieOptions());
  return res;
}
