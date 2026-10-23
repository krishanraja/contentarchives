import { NextRequest, NextResponse } from "next/server";
import { admit, checkCode, cleanCode, join, lock, normEmail, normName, person, sendCode, start, type Checked } from "@/lib/access";
import { clientIp, ipHash } from "@/lib/gate";
import { need } from "@/lib/env";
import { ASKING, ASKING_AGE, COOKIE, ME, cookieOptions, sign, signAsking, signMe, verifyAsking, verifyLink } from "@/lib/session";

// Every step of signing in is a plain form posted here, answered with the next
// page: it works on a slow phone before the page's script has arrived, and a
// person who comes back later carries on where they left off, because the
// email they typed is kept in a signed cookie.
const SAY: Record<string, string> = { wait: "wait", many: "many", mail: "mail", sent: "sent" };

export async function POST(req: NextRequest) {
  const form = await req.formData().catch(() => null);
  const get = (k: string) => String(form?.get(k) || "");
  const go = (to: string) => NextResponse.redirect(new URL(to, req.url), 303);
  const back = (said?: string) => go(said && SAY[said] ? `/gate?e=${SAY[said]}` : "/gate");
  const op = get("op");
  const ih = ipHash(clientIp(req.headers.get("x-forwarded-for")), need("SESSION_SECRET"));
  const site = req.nextUrl.origin;

  if (op === "reset") {
    const res = go("/gate");
    res.cookies.delete(ASKING);
    return res;
  }

  if ((await lock(ih)) !== "ok") return go("/gate?e=locked");

  if (op === "start") {
    const email = normEmail(get("email"));
    if (!email) return go("/gate?e=email");
    const res = back(await start(email, ih, site));   // "new" and "no" are shown from the cookie
    res.cookies.set(ASKING, await signAsking(email), cookieOptions(ASKING_AGE));
    return res;
  }

  // the button on the page a sign-in email's link opened: its code, as if typed
  if (op === "link") {
    const l = await verifyLink(get("t"));
    if (!l) return go("/gate?e=old");
    const out = await checkCode(l.email, l.code, ih);
    // a link that no longer works carries on at the code step, with "Send again"
    const res = await signedIn(out.ok || out.why !== "wrong" ? out : { ok: false, why: "old" });
    if (!out.ok) res.cookies.set(ASKING, await signAsking(l.email), cookieOptions(ASKING_AGE));
    return res;
  }

  const email = await verifyAsking(req.cookies.get(ASKING)?.value);
  if (!email) return go("/gate");

  if (op === "join") {
    const name = normName(get("name"));
    if (!name) return go("/gate?e=name");
    return back(await join(email, name, ih, site));
  }
  if (op === "resend") {
    const p = await person(email);
    return back(p && p.status !== "no" ? await sendCode(await admit(p), ih, site) : undefined);
  }
  if (op === "code") return signedIn(await checkCode(email, cleanCode(get("code")), ih));
  return go("/gate");

  async function signedIn(out: Checked) {
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
}
