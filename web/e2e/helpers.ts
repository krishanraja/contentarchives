import { expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import postgres from "postgres";
import { existsSync, readFileSync } from "node:fs";

// One connection pool for every spec file in the worker: no file ends it (the
// next file would find it closed); it closes itself when idle.
export const db = postgres(process.env.DATABASE_URL || "postgres://postgres:pw@127.0.0.1:54329/arch", { prepare: false, max: 2, idle_timeout: 5 });

// Every email the app sends goes to this file in local tests (MAIL_SINK in
// .env.local); the owner's address.
export const MAIL = process.env.MAIL_SINK || "/tmp/archives-mail.jsonl";
export const ADMIN = process.env.ACCESS_ADMIN_EMAIL || "admin@family.test";
export const emailOf = (name: string) => `${name.toLowerCase().replace(/[^a-z]+/g, ".")}@family.test`;

export type Sent = { to: string; subject: string; text: string; html: string; at: string };
export function mails(to?: string): Sent[] {
  if (!existsSync(MAIL)) return [];
  return readFileSync(MAIL, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as Sent)
    .filter((m) => !to || m.to === to);
}
// the next email to an address, once there are more than `before` of them
export async function nextMail(to: string, before: number): Promise<Sent> {
  for (let i = 0; i < 100; i++) {
    const m = mails(to);
    if (m.length > before) return m[m.length - 1];
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`no email arrived for ${to}`);
}
export const codeIn = (m: Sent) => /code is (\d{6})/.exec(m.text)![1];
export const linkIn = (m: Sent) => /(https?:\/\/\S+\/in\?t=\S+)/.exec(m.text)![1];

// Someone who has signed in before. A test signs the same person in many
// times an hour, so the hourly cap on codes starts afresh for them.
export async function letIn(name: string) {
  const email = emailOf(name);
  await db`insert into access_people (email, name, status, decided_at) values (${email}, ${name}, 'yes', now())
    on conflict (email) do update set status = 'yes', name = excluded.name, tries = 0`;
  await db`delete from access_sends where email = ${email}`;
  return email;
}

// Signing in as a person does: their email, then the code emailed to them.
// `email` signs in under that address instead (the owner's, ADMIN).
export async function signIn(page: Page, name = "Grandma", email?: string) {
  if (email) {
    await db`insert into access_people (email, name, status, decided_at) values (${email}, ${name}, 'yes', now())
      on conflict (email) do update set status = 'yes', name = excluded.name, tries = 0`;
    await db`delete from access_sends where email = ${email}`;
  } else email = await letIn(name);
  const before = mails(email).length;
  await page.goto("/gate");
  const other = page.locator("button:has-text('Change email'), button:has-text('Use a different email')");
  if (await other.count()) await other.first().click();
  await page.fill("#email", email);
  await page.click("button:has-text('Email me a link')");
  await page.fill("#code", codeIn(await nextMail(email, before)));
  await page.click("button:has-text('Open')");
  await page.waitForURL((u) => u.pathname === "/");
}

// The floor older users are owed on every screen: one step down from 56px
// controls and 20px text (Krish, 2026-10-11), and no further.
export async function floor(page: Page, where: string) {
  await page.waitForLoadState("networkidle");
  const m = await page.evaluate(() => {
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    };
    const small = [...document.querySelectorAll("button, a.btn, a.chip, a.tile, input, .grid a, .pill a")]
      .filter(visible)
      .filter((el) => el.getBoundingClientRect().height < 47.5)
      .map((el) => (el.textContent || el.getAttribute("aria-label") || el.tagName).trim().slice(0, 30));
    const tiny = [...document.querySelectorAll("p, li, label, button, a, input, span")]
      .filter(visible)
      .filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && (n.textContent || "").trim()))
      .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 14)
      .map((el) => (el.textContent || "").trim().slice(0, 30));
    const body = parseFloat(getComputedStyle(document.body).fontSize);
    return { overflow: document.documentElement.scrollWidth - window.innerWidth, small, tiny, body };
  });
  expect(m.overflow, `${where}: sideways scrolling`).toBeLessThanOrEqual(0);
  expect(m.small, `${where}: controls under 48px`).toEqual([]);
  expect(m.tiny, `${where}: text under 14px`).toEqual([]);
  expect(m.body, `${where}: body text`).toBeGreaterThanOrEqual(18);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .exclude("nextjs-portal").analyze();
  expect(axe.violations.map((v) => `${v.id}: ${v.nodes.length}`), `${where}: accessibility`).toEqual([]);
}
