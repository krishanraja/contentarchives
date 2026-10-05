import { expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import postgres from "postgres";

// One connection pool for every spec file in the worker: no file ends it (the
// next file would find it closed); it closes itself when idle.
export const db = postgres(process.env.DATABASE_URL || "postgres://postgres:pw@127.0.0.1:54329/arch", { prepare: false, max: 2, idle_timeout: 5 });

export async function signIn(page: Page, name = "Grandma") {
  await page.goto("/gate");
  await page.fill("#code", "sunflower");
  await page.click("button:has-text('Open')");
  await page.waitForURL("**/who");
  await page.click(`button:has-text('${name}')`);
  await page.waitForURL((u) => u.pathname === "/");
}

// The floor older users are owed on every screen.
export async function floor(page: Page, where: string) {
  await page.waitForLoadState("networkidle");
  const m = await page.evaluate(() => {
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    };
    const small = [...document.querySelectorAll("button, a.btn, a.chip, a.tile, input, .grid a")]
      .filter(visible)
      .filter((el) => el.getBoundingClientRect().height < 55.5)
      .map((el) => (el.textContent || el.getAttribute("aria-label") || el.tagName).trim().slice(0, 30));
    const tiny = [...document.querySelectorAll("p, li, label, button, a, input, span")]
      .filter(visible)
      .filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && (n.textContent || "").trim()))
      .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
      .map((el) => (el.textContent || "").trim().slice(0, 30));
    const body = parseFloat(getComputedStyle(document.body).fontSize);
    return { overflow: document.documentElement.scrollWidth - window.innerWidth, small, tiny, body };
  });
  expect(m.overflow, `${where}: sideways scrolling`).toBeLessThanOrEqual(0);
  expect(m.small, `${where}: controls under 56px`).toEqual([]);
  expect(m.tiny, `${where}: text under 16px`).toEqual([]);
  expect(m.body, `${where}: body text`).toBeGreaterThanOrEqual(20);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .exclude("nextjs-portal").analyze();
  expect(axe.violations.map((v) => `${v.id}: ${v.nodes.length}`), `${where}: accessibility`).toEqual([]);
}
