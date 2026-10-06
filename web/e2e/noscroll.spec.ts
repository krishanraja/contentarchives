import { expect, test, type Page } from "@playwright/test";
import { execSync } from "node:child_process";
import { db, signIn } from "./helpers";

// NOTHING SCROLLS, ON ANY DEVICE (Krish, 2026-10-05: "this needs to be
// guaranteed no scroll on all devices"). Every screen, in every state a
// person can reach, at every size below: the page does not move, every
// button is wholly on screen and is the thing a finger lands on, no words
// spill out of their box or sit on top of another box, and a photo stays big
// enough to recognise someone in.
//
// The sizes are what a page really GETS inside a phone's browser - the screen
// less the address bar, the toolbar and the system bar - not the screen
// itself. Krish's phone, 2026-10-06: a 412x915 screen gives Chrome's page
// 412x748, and a layout tested only at 412x915 broke on it.
const SIZES: [number, number][] = [
  [320, 460], [360, 560], [375, 553], [390, 664], [393, 727], [412, 748], [430, 740],  // in a phone's browser, upright
  [412, 806], [375, 667], [390, 844], [430, 932],                                      // address bar hidden; full screen
  [568, 280], [667, 325], [844, 340], [915, 356],                                      // in a phone's browser, on its side
  [768, 954], [1024, 698], [1280, 720], [1920, 960],                                   // tablets and computers, in a browser
];

test.describe.configure({ mode: "serial" });
// The layout itself, at each size: the "Desktop site" rescue in layout.tsx,
// which scales a page up on a touch screen, has its own test in flows.spec.ts.
test.use({ actionTimeout: 15_000, hasTouch: false, isMobile: false, deviceScaleFactor: 1 });
test.beforeAll(() => {
  execSync("npx tsx scripts/seed-fixtures.ts", { stdio: "ignore", env: { ...process.env, IMAGE_SOURCE: "fixture",
    DATABASE_URL: process.env.DATABASE_URL || "postgres://postgres:pw@127.0.0.1:54329/arch" } });
});

const failures: string[] = [];
const shot = new Set<string>();

async function settle(page: Page) {
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(60);
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
}

async function fits(page: Page, where: string) {
  await page.waitForLoadState("networkidle");
  for (const [w, h] of SIZES) {
    await page.setViewportSize({ width: w, height: h });
    await settle(page);
    const bad = await page.evaluate(() => {
      const out: string[] = [];
      const d = document.documentElement;
      if (d.scrollHeight > innerHeight + 1) out.push(`scrolls down ${d.scrollHeight - innerHeight}px`);
      if (d.scrollWidth > innerWidth + 1) out.push(`scrolls sideways ${d.scrollWidth - innerWidth}px`);
      for (const el of document.querySelectorAll<HTMLElement>("button, a[href], input:not([type=hidden]), summary, textarea, select")) {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2 || !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
        if (el.closest("[aria-hidden=true]")) continue;
        const name = (el.textContent || el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.tagName).trim().slice(0, 28);
        if (r.top < -1 || r.left < -1 || r.bottom > innerHeight + 1 || r.right > innerWidth + 1) {
          out.push(`off screen: "${name}"`);
          continue;
        }
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        if (!hit || !(hit === el || el.contains(hit))) out.push(`covered: "${name}"`);
      }
      // words that spill out of their box, onto whatever is next to it
      const seen = (el: Element) => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1 && el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) && !el.closest("[aria-hidden=true]"); };
      const label = (el: Element) => ((el as HTMLElement).innerText || el.className || el.tagName).toString().replace(/\s+/g, " ").trim().slice(0, 28);
      for (const el of document.querySelectorAll<HTMLElement>(".page *, .bar *")) {
        if (!seen(el) || getComputedStyle(el).display === "inline") continue;
        const cs = getComputedStyle(el);
        if (cs.overflowY === "visible" && el.scrollHeight > el.clientHeight + 2) out.push(`spills out of its box: "${label(el)}"`);
        if (cs.overflowX === "visible" && el.scrollWidth > el.clientWidth + 2) out.push(`spills sideways: "${label(el)}"`);
      }
      // boxes laid out side by side or one under another that sit on top of each other
      const flow = (p: Element): Element[] => [...p.children].flatMap((k) =>
        getComputedStyle(k).display === "contents" ? flow(k) : [k]);
      for (const p of [document.querySelector(".screen")!, ...document.querySelectorAll(".screen *")]) {
        if (!/flex|grid/.test(getComputedStyle(p).display)) continue;
        const kids = flow(p).filter((k) => seen(k) && !/absolute|fixed/.test(getComputedStyle(k).position));
        for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++) {
          const a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
          const x = Math.min(a.right, b.right) - Math.max(a.left, b.left), y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          if (x > 2 && y > 2) out.push(`on top of each other: "${label(kids[i])}" / "${label(kids[j])}"`);
        }
      }
      const shot = document.querySelector(".slot");
      if (shot) {
        const sh = shot.getBoundingClientRect().height;
        if (sh < Math.min(120, innerHeight * 0.28)) out.push(`photo only ${Math.round(sh)}px tall`);
      }
      return out;
    });
    for (const b of bad) failures.push(`${where} @ ${w}x${h}: ${b}`);
    if (bad.length && process.env.NOSCROLL_SHOTS && !shot.has(where)) {
      shot.add(where);
      await page.screenshot({ path: `${process.env.NOSCROLL_SHOTS}/${where.replace(/[^a-z0-9]+/gi, "-")}-${w}x${h}.png` });
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await settle(page);
}

test("every screen, in every state, fits every screen size without scrolling", async ({ page, browser }, info) => {
  test.skip(info.project.name !== "390");
  test.setTimeout(1_200_000);
  failures.length = 0;

  // the gate, and the gate inside WhatsApp (an extra notice)
  await page.goto("/gate");
  await fits(page, "gate");
  await page.fill("#code", "wrong");
  await page.click("button:has-text('Open')");
  await expect(page.getByText("That's not it")).toBeVisible();
  await fits(page, "gate, wrong code");
  const wa = await browser.newContext({ userAgent: "Mozilla/5.0 (Linux; Android 14) WhatsApp/2.24" });
  const wap = await wa.newPage();
  await wap.goto("/gate");
  await fits(wap, "gate in WhatsApp");
  await wa.close();

  // who are you: the family's names, and someone else
  await page.fill("#code", "sunflower");
  await page.click("button:has-text('Open')");
  await page.waitForURL("**/who");
  await fits(page, "who");
  await page.click("summary:has-text('Someone else')");
  await fits(page, "who, someone else");
  await page.click("summary:has-text('Someone else')");       // closed again: the names come back
  await page.click("button:has-text('Grandma')");
  await page.waitForURL((u) => u.pathname === "/");
  await fits(page, "home");

  // a long place name, as the live library has (43 letters)
  await db`update photos set place = 'Shri Venkateswara Temple, Tirumala Hills' where hash = (select hash from photos where place = 'Goa' limit 1)`;
  await page.goto("/find");
  await fits(page, "find");
  for (const tab of ["Places", "Years"]) {
    const t = page.locator(`a:has-text('${tab}'), button:has-text('${tab}')`).first();
    if (await t.count()) { await t.click(); await page.waitForLoadState("networkidle"); await fits(page, `find, ${tab}`); }
  }
  await page.goto("/find?q=Asha");
  await fits(page, "results");
  const more = page.locator("button:has-text('More')");
  if (await more.isVisible()) { await more.click(); await fits(page, "results, next page"); }
  await page.goto("/find?q=zebra%20crossing%201871");
  await fits(page, "results, nothing found");

  // a photo with the longest description and the most people the live library has
  await page.goto("/find?q=Asha");
  const first = await page.locator(".grid a").first().getAttribute("href");
  const hash = decodeURIComponent(first!.split("/photo/")[1].split("?")[0]);
  await db`update photos set description = ${"A long afternoon in the garden with everyone gathered round the table under the old mango tree, plates of food, children running between the chairs, a dog asleep in the shade, grandparents in the middle laughing at something just out of the picture, cousins on the steps, and the light coming low through the leaves so every face is half in sun. ".repeat(2).slice(0, 556)},
             people = ${["Asha Raja", "Ravi Raja", "Meera Shah", "Dev Shah", "Priya Kapoor", "Sam Kapoor", "Kamala Raja", "Sunil Raja", "Usha Raja", "Ashvin Raja", "Isha Patel", "Tara Patel", "Vikram Patel"]}::text[]
           where hash = ${hash}`;
  await page.goto(first!);
  await fits(page, "photo");
  const about = page.locator("button:has-text('About this photo')");
  if (await about.count()) { await about.click(); await fits(page, "photo, about"); }

  // who is this: every question it can ask
  await page.goto("/help");
  await expect(page.getByText("Is this Ravi Raja?")).toBeVisible();
  await fits(page, "who is this, yes/no");
  await page.click("button:has-text('No')");
  await fits(page, "who is this, choose");
  await page.click("button:has-text('Someone else')");
  await page.fill("#nm", "a");
  await fits(page, "who is this, typing");
  await page.fill("#nm", "Meera Sha");
  await page.click("button:has-text('Save this name')");
  await expect(page.getByText("Did you mean Meera Shah?")).toBeVisible();
  await fits(page, "who is this, did you mean");
  await page.click("[aria-label='Names we already know'] button:has-text('Meera Shah')");
  await expect(page.getByText("now say")).toBeVisible();
  await fits(page, "who is this, thank you + undo");
  // a tie: two people, two names
  for (const [who, name] of [["grandpa", "Asha Raja"], ["auntie meera", "Priya Kapoor"]])
    await db`insert into answers (id, who, scope, target, field, value) values (gen_random_uuid(), ${who}, 'cluster', 'c8', 'person', ${name})`;
  await page.goto("/help");
  await expect(page.getByText("People said different names")).toBeVisible();
  await fits(page, "who is this, contested");
  await page.click("button:has-text(\"I don't know\")");
  await expect(page.getByText("That's every face for now")).toBeVisible();
  await fits(page, "who is this, every face seen");

  // where and when: every step
  await page.goto("/story");
  await expect(page.getByText("Where was this taken?")).toBeVisible();
  await fits(page, "where, chips");
  await page.click("button:has-text('Somewhere else')");
  await fits(page, "where, typing");
  await page.fill("#pl", "Bri ghton");
  await page.click("button:has-text('Save this place')");
  await expect(page.getByText("Did you mean Brighton?")).toBeVisible();
  await fits(page, "where, did you mean");
  await page.click("[aria-label='Places we already know'] button:has-text('Brighton')");
  const day = page.getByText(/Also label the \d+ other/);
  await expect(day.or(page.getByText("Roughly what year?")).or(page.getByText("Thank you!"))).toBeVisible();
  if (await day.isVisible()) {
    await fits(page, "where, the whole day");
    await page.click("button:has-text('Just this one')");
  }
  if (await page.getByText("Roughly what year?").isVisible()) {
    await fits(page, "when, decade");
    await page.click("button:has-text('1980s')");
    await fits(page, "when, year");
    await page.click("button:has-text('1987')");
  }
  await expect(page.getByText("Thank you!").or(page.getByText("labelled"))).toBeVisible();
  await fits(page, "where and when, thank you + undo");

  expect(failures, failures.join("\n")).toEqual([]);
});
