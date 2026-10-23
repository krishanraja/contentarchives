import { createHash, randomInt } from "node:crypto";
import type postgres from "postgres";
import { sql } from "./db";
import { need } from "./env";
import { lockState, type Lock } from "./gate";
import { codeMail, send, type Mail } from "./mail";
import { signLink } from "./session";

// Signing in (Krish, 2026-10-23: "I don't need to approve every new user"): a
// person types their email (and, the first time, their first name) and is
// emailed a link that opens the app, with the same six-digit code beside it
// for a phone whose link opens in another browser. Nobody waits for Krish; he
// can still stop someone (status 'no'). Addresses and names live only in the
// database (migration 0016); a code is stored only as a keyed hash.
//
// EVERY LIMIT IS TAKEN, NOT JUST READ. A limit that is read and only recorded
// afterwards lets a burst of requests sent at once all read "under the limit"
// and all go through. So each check and its record happen in one transaction
// that holds a lock on the address: a burst queues up behind the lock and meets the limit one request at a time.

export const CODE_MINUTES = 30;               // a link and its code, from when it is sent
export const MAX_TRIES = 5;                   // wrong codes, then every live code stops working
export const LIVE_CODES = 2;                  // codes that work at once: a late email's, and the newest
export const RESEND_SECONDS = 60;             // one code a minute to the same address
export const CODES_PER_HOUR = 6;              // and no more than this an hour
export const CODES_PER_IP_HOUR = 30;          // to anyone, from one network
export const CODES_PER_HOUR_ALL = 200;        // and from everywhere

// "asked" is only ever an address from before 2026-10-23 that was waiting for
// Krish: it is let in the next time it signs in.
export type Person = { email: string; name: string; status: "asked" | "yes" | "no" };
export type Step = "email" | "name" | "no" | "code";

// Case and spaces are not part of an address; anything that is not shaped like
// one is refused before it reaches the database.
export function normEmail(s: unknown): string | null {
  const e = String(s ?? "").normalize("NFKC").trim().toLowerCase();
  return e.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e) ? e : null;
}

// The same rule as a name typed on "Who are you?" (api/who).
export function normName(s: unknown): string | null {
  const n = String(s ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").slice(0, 40);
  return n.length >= 2 ? n : null;
}

// "123 456", "123-456" and a pasted "Your code is 123456" are all 123456.
export function cleanCode(s: unknown): string {
  return String(s ?? "").normalize("NFKC").replace(/\D/g, "").slice(0, 6);
}

export function newCode(): string {
  return String(randomInt(0, 1_000_000)).padStart(6, "0");
}

// Keyed by the app's secret and the address, so a copy of the table alone
// gives up no code, and one person's code is never anyone else's.
export function codeHash(secret: string, email: string, code: string): string {
  return createHash("sha256").update(`${secret}|${email}|${code}`).digest("hex");
}

export function stepFor(email: string | null, status: Person["status"] | null): Step {
  if (!email) return "email";
  if (!status) return "name";
  return status === "no" ? "no" : "code";
}

const minutes = (n: number) => `${n} minutes`;
type Tx = postgres.TransactionSql;

// One transaction holding a lock on `key` until it ends.
async function locked<T>(key: string, work: (tx: Tx) => Promise<T>): Promise<T> {
  return (await sql().begin(async (tx) => {
    await tx`select pg_advisory_xact_lock(hashtext(${key}))`;
    return work(tx);
  })) as T;
}

// Sends, and says whether it went. A missing setting still stops loudly, but
// only after `undo` has taken back what was written for an email that never went.
async function deliver(m: Mail, undo: () => Promise<unknown>): Promise<boolean> {
  let ok = false;
  try {
    ok = await send(m);
  } finally {
    if (!ok) await undo();
  }
  return ok;
}

export async function person(email: string): Promise<Person | null> {
  const [p] = await sql()`select email, name, status from access_people where email = ${email}`;
  return (p as Person | undefined) || null;
}

export async function lock(ih: string): Promise<Lock> {
  const [c] = await sql()`select
      count(*) filter (where ip_hash = ${ih} and not ok)::int ip,
      count(*) filter (where not ok)::int total
    from gate_attempts where at > now() - interval '1 hour'`;
  return lockState(c.ip, c.total);
}

// Someone who was waiting for Krish's yes from before 2026-10-23 no longer waits.
export async function admit(p: Person): Promise<Person> {
  if (p.status !== "asked") return p;
  await sql()`update access_people set status = 'yes', decided_at = now() where email = ${p.email} and status = 'asked'`;
  return { ...p, status: "yes" };
}

export type Sent = "sent" | "wait" | "many" | "mail";

// A new link and code, emailed. The one before it still works until it runs
// out, so an email that arrived late is not wrongly refused; any older ones
// stop. A new code also gives back the wrong tries.
export async function sendCode(p: Person, ih: string, site: string): Promise<Sent> {
  const code = newCode();
  const life = CODE_MINUTES;
  const made = await locked(`code:${p.email}`, async (tx) => {
    const [s] = await tx`select
        max(at) filter (where email = ${p.email}) as last,
        count(*) filter (where email = ${p.email} and at > now() - interval '1 hour')::int as mine,
        count(*) filter (where ip_hash = ${ih} and at > now() - interval '1 hour')::int as net,
        count(*) filter (where at > now() - interval '1 hour')::int as total
      from access_sends where kind = 'code' and at > now() - interval '1 hour'`;
    const [l] = await tx`select count(*)::int as n from access_codes
      where email = ${p.email} and used_at is null and expires_at > now()`;
    // the minute's wait is for a code still on its way, not after one stopped working
    if (l.n && s.last && Date.now() - new Date(s.last).getTime() < RESEND_SECONDS * 1000) return "wait";
    if (s.mine >= CODES_PER_HOUR || s.net >= CODES_PER_IP_HOUR || s.total >= CODES_PER_HOUR_ALL) return "many";
    await tx`insert into access_sends (kind, email, ip_hash) values ('code', ${p.email}, ${ih})`;
    await tx`update access_codes set used_at = now()
      where email = ${p.email} and used_at is null and id not in (
        select id from access_codes where email = ${p.email} and used_at is null and expires_at > now()
        order by id desc limit ${LIVE_CODES - 1})`;
    await tx`update access_people set tries = 0 where email = ${p.email}`;
    const [row] = await tx`insert into access_codes (email, code_hash, expires_at)
      values (${p.email}, ${codeHash(need("SESSION_SECRET"), p.email, code)}, now() + ${minutes(life)}::interval)
      returning id`;
    return row.id as string;
  });
  if (made === "wait" || made === "many") return made;
  const link = `${site}/in?t=${encodeURIComponent(await signLink(p.email, code, life * 60))}`;
  const went = await deliver(codeMail(p.email, p.name, code, { minutes: life, link }),
    () => sql()`delete from access_codes where id = ${made}`);
  return went ? "sent" : "mail";
}

// An email typed on the sign-in screen: someone known gets a link and code;
// anyone new is asked their first name next.
export async function start(email: string, ih: string, site: string): Promise<Sent | "new" | "no"> {
  const found = await person(email);
  if (!found) return "new";
  if (found.status === "no") return "no";
  return sendCode(await admit(found), ih, site);
}

// A new person's first name: they are in, and emailed a link and code. The
// caps on codes (per address, per network, in all) are what bound sign-ups.
export async function join(email: string, name: string, ih: string, site: string): Promise<Sent | "no"> {
  await sql()`insert into access_people (email, name, status, decided_at) values (${email}, ${name}, 'yes', now())
    on conflict (email) do nothing`;
  const p = await person(email);
  if (!p || p.status === "no") return "no";
  return sendCode(await admit(p), ih, site);
}

export type Checked = { ok: true; name: string } | { ok: false; why: "wrong" | "old" | "spent" };

// A try is TAKEN before the code is looked at, under the address's lock, so a
// burst of guesses gets MAX_TRIES of them and no more. Only a good code or a
// new one gives the tries back.
export async function checkCode(email: string, code: string, ih: string): Promise<Checked> {
  const h = codeHash(need("SESSION_SECRET"), email, code);
  return locked(`code:${email}`, async (tx): Promise<Checked> => {
    const [p] = await tx`update access_people set tries = tries + 1
      where email = ${email} and status = 'yes' and tries < ${MAX_TRIES} returning name, tries`;
    if (!p) {
      await tx`insert into gate_attempts (ip_hash, ok) values (${ih}, false)`;
      const [spent] = await tx`select 1 from access_people where email = ${email} and status = 'yes'`;
      return { ok: false, why: spent ? "spent" : "wrong" };
    }
    const [hit] = code.length === 6 ? await tx`update access_codes set used_at = now()
      where email = ${email} and code_hash = ${h} and used_at is null and expires_at > now() returning id` : [];
    if (hit) {
      await tx`update access_codes set used_at = now() where email = ${email} and used_at is null`;
      await tx`update access_people set tries = 0 where email = ${email}`;
      await tx`insert into gate_attempts (ip_hash, ok) values (${ih}, true)`;
      return { ok: true, name: p.name as string };
    }
    await tx`insert into gate_attempts (ip_hash, ok) values (${ih}, false)`;
    if ((p.tries as number) >= MAX_TRIES) {
      await tx`update access_codes set used_at = now() where email = ${email} and used_at is null`;
      return { ok: false, why: "spent" };
    }
    const [old] = await tx`select count(*)::int as n from access_codes
      where email = ${email} and code_hash = ${h} and used_at is null and expires_at <= now()`;
    return { ok: false, why: old.n ? "old" : "wrong" };
  });
}
