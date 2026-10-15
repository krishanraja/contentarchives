import { NextRequest, NextResponse } from "next/server";
import { ask, checkCode, cleanCode, decide, lock, normEmail, normName, person, sendCode, start } from "@/lib/access";
import { clientIp, ipHash } from "@/lib/gate";
import { need } from "@/lib/env";
import { ASKING, ASKING_AGE, COOKIE, ME, cookieOptions, sign, signAsking, signMe, verifyAsking } from "@/lib/session";

// Every step of signing in is a plain form posted here, answered with the next
// page: it works on a slow phone before the page's script has arrived, and a
// person who comes back days later (after Krish says yes) carries on where
// they left off, because the email they typed is kept in a signed cookie.
const SAY: Record<string, string> = { wait: "wait", many: "many", mail: "mail", busy: "busy", asked: "asked", sent: "sent", reminded: "reminded" };

export async function POST(req: NextRequest) {
  const form = await req.formData().catch(() => null);
  const get = (k: string) => String(form?.get(k) || "");
  const go = (to: string) => NextResponse.redirect(new URL(to, req.url), 303);
  const back = (said?: string) => go(said && SAY[said] ? `/gate?e=${SAY[said]}` : "/gate");
  const op = get("op");
  const ih = ipHash(clientIp(req.headers.get("x-forwarded-for")), need("SESSION_SECRET"));
  const site = req.nextUrl.origin;

  // Krish's yes or no, from the page his emailed link opened
  if (op === "decide") {
    const t = get("t");
    const out = await decide(t, get("d") === "yes", ih, site);
    return go(`/approve?t=${encodeURIComponent(t)}${out === "yes-mail" ? "&e=mail" : ""}`);
  }
  if (op === "reset") {
    const res = go("/gate");
    res.cookies.delete(ASKING);
    return res;
  }

  if ((await lock(ih)) !== "ok") return go("/gate?e=locked");

  if (op === "start") {
    const email = normEmail(get("email"));
    if (!email) return go("/gate?e=email");
    const res = back(await start(email, ih, site));
    res.cookies.set(ASKING, await signAsking(email), cookieOptions(ASKING_AGE));
    return res;
  }

  const email = await verifyAsking(req.cookies.get(ASKING)?.value);
  if (!email) return go("/gate");

  if (op === "ask") {
    const name = normName(get("name"));
    if (!name) return go("/gate?e=name");
    return back(await ask(email, name, ih, site));
  }
  if (op === "resend") {
    const p = await person(email);
    return back(p?.status === "yes" ? await sendCode(p, ih, site) : undefined);
  }
  if (op === "code") {
    const out = await checkCode(email, cleanCode(get("code")), ih);
    if (!out.ok) {
      if ((await lock(ih)) === "global" && process.env.ALERT_WEBHOOK_URL) {
        await fetch(process.env.ALERT_WEBHOOK_URL, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ text: "archives.krishraja.com: sign-in locked after too many wrong codes" }),
        }).catch(() => undefined);
      }
      return go(`/gate?e=${out.why}`);
    }
    const who = out.name.toLowerCase();
    const res = go("/");
    res.cookies.set(COOKIE, await sign(who, "email"), cookieOptions());
    res.cookies.set(ME, await signMe(who), cookieOptions());
    res.cookies.delete(ASKING);
    return res;
  }
  return go("/gate");
}
