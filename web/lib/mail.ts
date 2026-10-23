import { appendFile } from "node:fs/promises";
import { need } from "./env";

// Every email the app sends: a sign-in link and code to a person. Sent through Resend; never logged, because an address and
// a code are exactly what must not end up in a log.
export type Mail = { to: string; subject: string; text: string; html: string };

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const page = (body: string) =>
  `<div style="font-family:system-ui,sans-serif;font-size:20px;line-height:1.5;color:#1e1433;max-width:520px">${body}</div>`;

export function codeMail(to: string, name: string, code: string, opts: { minutes: number; link: string }): Mail {
  const lasts = `${opts.minutes} minutes`;
  return {
    to,
    subject: `Your Family Archives link (code ${code})`,
    text: `Hello ${name},\n\nTap this link to open the Family Archives:\n${opts.link}\n\n`
      + `Or type this code on the Family Archives page: your code is ${code}\n\nBoth work for the next ${lasts}.\n\n`
      + `If you did not ask for this, you can ignore this email.\n`,
    html: page(`<p>Hello ${esc(name)},</p>`
      + `<p style="margin:24px 0"><a href="${esc(opts.link)}" style="display:inline-block;background:#ffc93c;color:#1e1433;border:3px solid #1e1433;border-radius:16px;padding:12px 22px;font-weight:700;text-decoration:none">Open the Family Archives</a></p>`
      + `<p>Or type this code on the Family Archives page:</p>`
      + `<p style="font-size:36px;font-weight:700;letter-spacing:6px;margin:16px 0">${code}</p>`
      + `<p>Both work for the next ${lasts}.</p>`
      + `<p style="color:#5b5068;font-size:16px">If you did not ask for this, you can ignore this email.</p>`),
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
