import { appendFile } from "node:fs/promises";
import { need } from "./env";

// Every email the app sends: a code to a person, or "someone would like to
// come in" to Krish. Sent through Resend; never logged, because an address and
// a code are exactly what must not end up in a log.
export type Mail = { to: string; subject: string; text: string; html: string };

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const page = (body: string) =>
  `<div style="font-family:system-ui,sans-serif;font-size:20px;line-height:1.5;color:#1e1433;max-width:520px">${body}</div>`;

export function codeMail(to: string, name: string, code: string, opts: { minutes: number; approved: boolean; site: string }): Mail {
  const lasts = opts.minutes >= 120 ? `${Math.round(opts.minutes / 1440) || 1} days` : `${opts.minutes} minutes`;
  const lead = opts.approved ? "Krish said yes!" : "Here is your code for the Family Archives.";
  const how = opts.approved
    ? `Open ${opts.site}, type your email, then this code. It works for the next ${lasts}.`
    : `Type it on the Family Archives page to get in. It works for the next ${lasts}.`;
  return {
    to,
    subject: `${opts.approved ? "Krish said yes! " : ""}Your Family Archives code is ${code}`,
    text: `Hello ${name},\n\n${lead}\n\nYour code is ${code}\n\n${how}\n\nIf you did not ask for this, you can ignore this email.\n`,
    html: page(`<p>Hello ${esc(name)},</p><p>${esc(lead)}</p>`
      + `<p style="font-size:36px;font-weight:700;letter-spacing:6px;margin:24px 0">${code}</p>`
      + `<p>${opts.approved ? `Open <a href="${esc(opts.site)}">${esc(opts.site)}</a>, type your email, then this code. It works for the next ${lasts}.` : esc(how)}</p>`
      + `<p style="color:#5b5068;font-size:16px">If you did not ask for this, you can ignore this email.</p>`),
  };
}

export function askMail(to: string, name: string, email: string, link: string): Mail {
  return {
    to,
    subject: `${name} would like to see the Family Archives`,
    text: `${name} (${email}) asked to see the Family Archives.\n\nSay yes or no here:\n${link}\n\nNothing happens until you tap a button on that page.\n`,
    html: page(`<p><strong>${esc(name)}</strong> (${esc(email)}) asked to see the Family Archives.</p>`
      + `<p style="margin:24px 0"><a href="${esc(link)}" style="display:inline-block;background:#ffc93c;color:#1e1433;border:3px solid #1e1433;border-radius:16px;padding:12px 22px;font-weight:700;text-decoration:none">Say yes or no</a></p>`
      + `<p style="color:#5b5068;font-size:16px">Nothing happens until you tap a button on that page.</p>`),
  };
}

// Local tests write each email to a file instead (MAIL_SINK). Refused on
// Vercel, so a stray setting can never swallow the family's real emails.
export async function send(m: Mail): Promise<boolean> {
  const sink = process.env.MAIL_SINK;
  if (sink) {
    if (process.env.VERCEL) throw new Error("MAIL_SINK is for local tests only");
    await appendFile(sink, JSON.stringify({ ...m, at: new Date().toISOString() }) + "\n");
    return true;
  }
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${need("RESEND_API_KEY")}`, "content-type": "application/json" },
    body: JSON.stringify({ from: need("MAIL_FROM"), to: [m.to], subject: m.subject, text: m.text, html: m.html }),
    signal: AbortSignal.timeout(10_000),
  }).catch(() => null);
  return !!r?.ok;
}
