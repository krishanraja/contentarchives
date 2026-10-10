import { expect, test } from "@playwright/test";
import { execSync } from "node:child_process";
import { db, floor, signIn } from "./helpers";

test.describe.configure({ mode: "serial" });

// Every phone width starts from the same fresh synthetic family: answers
// saved at 360px must not change what 390px is asked.
test.beforeAll(() => {
  execSync("npx tsx scripts/seed-fixtures.ts", { stdio: "ignore", env: { ...process.env, IMAGE_SOURCE: "fixture",
    DATABASE_URL: process.env.DATABASE_URL || "postgres://postgres:pw@127.0.0.1:54329/arch" } });
});

test("a wrong code is refused kindly, the right one lets you in", async ({ page }) => {
  await page.goto("/gate");
  await floor(page, "gate");
  await page.fill("#code", "not it");
  await page.click("button:has-text('Open')");
  await expect(page.getByText("That's not it")).toBeVisible();
  await page.fill("#code", "  Sunflower ");
  await page.click("button:has-text('Open')");
  await page.waitForURL("**/who");
  await floor(page, "who");
  await page.click("button:has-text('Grandma')");
  await page.waitForURL((u) => u.pathname === "/");
  await expect(page.getByRole("heading", { name: "Hello, Grandma!" })).toBeVisible();
  await floor(page, "home");
});

test("the code and a name work before the page's script has arrived", async ({ browser }) => {
  // a slow phone: the page is on screen, the script is not - every tap must still work
  const ctx = await browser.newContext({ javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto("/gate");
  await page.fill("#code", "wrong");
  await page.click("button:has-text('Open')");
  await expect(page.getByText("That's not it")).toBeVisible();
  await page.fill("#code", "sunflower");
  await page.click("button:has-text('Open')");
  await page.waitForURL("**/who");
  await page.click("summary:has-text('Someone else')");
  await page.fill("#me", "Cousin Tara");
  await page.click("button:has-text('That')");
  await page.waitForURL((u) => u.pathname === "/");
  await expect(page.getByRole("heading", { name: "Hello, Cousin Tara!" })).toBeVisible();
  await page.goto("/find");
  await page.fill("#q", "Asha");
  await page.click("button:has-text('Search')");
  await expect(page.locator(".sentence")).toContainText("of Asha Raja");
  await ctx.close();
});

test("with no names set up, it simply asks your name; and a shared phone can change person", async ({ page }) => {
  const saved = await db`select name, sort from players`;
  await db`delete from players`;
  try {
    await page.goto("/gate");
    await page.fill("#code", "sunflower");
    await page.click("button:has-text('Open')");
    await page.waitForURL("**/who");
    await expect(page.getByRole("heading", { name: "Hello! What's your name?" })).toBeVisible();
    await expect(page.locator("summary")).toHaveCount(0);           // no extra tap to reach the box
    await page.fill("#me", "Aunty Usha");
    await page.click("button:has-text('That')");
    await page.waitForURL((u) => u.pathname === "/");
    await expect(page.getByRole("heading", { name: "Hello, Aunty Usha!" })).toBeVisible();
    await floor(page, "home-named");
    await page.click("text=Not Aunty Usha? Tap here");
    await page.waitForURL("**/who");
    await page.fill("#me", "Dadi");
    await page.click("button:has-text('That')");
    await expect(page.getByRole("heading", { name: "Hello, Dadi!" })).toBeVisible();
  } finally {
    for (const p of saved) await db`insert into players (name, sort) values (${p.name}, ${p.sort}) on conflict do nothing`;
  }
});

test("a phone asking for the desktop page still gets the phone page", async ({ browser }) => {
  // Krish's phone: 412 px wide, Chrome laying pages out 1,040 px wide ("Desktop site")
  const ctx = await browser.newContext({ viewport: { width: 1040, height: 2253 }, screen: { width: 412, height: 892 },
    hasTouch: true, isMobile: false });
  const page = await ctx.newPage();
  await page.goto("/gate");
  const fit = await page.evaluate(() => ({ zoom: Number(getComputedStyle(document.documentElement).zoom),
    over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    down: document.documentElement.scrollHeight - document.documentElement.clientHeight }));
  expect(fit.zoom).toBeCloseTo(1040 / 412, 2);          // laid out at the phone's own width
  expect(fit.over).toBeLessThanOrEqual(0);              // and nothing runs off the side
  expect(fit.down).toBeLessThanOrEqual(1);              // or off the bottom: one screen, scaled or not
  await ctx.close();
  // a computer, and a phone that lays out at its own width, are left alone
  for (const opts of [{ viewport: { width: 1280, height: 800 } },
                      { viewport: { width: 412, height: 892 }, screen: { width: 412, height: 892 }, hasTouch: true, isMobile: true },
                      // an iPhone on its side reports its UPRIGHT width: still its own page, not blown up
                      { viewport: { width: 844, height: 390 }, screen: { width: 390, height: 844 }, hasTouch: true, isMobile: true }]) {
    const c = await browser.newContext(opts);
    const p = await c.newPage();
    await p.goto("/gate");
    expect(await p.evaluate(() => getComputedStyle(document.documentElement).zoom)).toBe("1");
    await c.close();
  }
});

test("nothing is reachable without the code", async ({ request }) => {
  for (const u of ["/", "/find", "/api/search?q=a", `/img/t/${"0".repeat(63)}1`, "/api/face/next"]) {
    const r = await request.get(u, { maxRedirects: 0 });
    expect([307, 401], u).toContain(r.status());
  }
});

test("find photos by a first name, a place and a year", async ({ page }) => {
  await signIn(page);
  await page.click("text=Find photos");
  await floor(page, "find");
  await page.fill("#q", "Ravi in Goa");
  await page.click("button:has-text('Search')");
  await page.waitForURL("**/find?q=*");
  await expect(page.locator(".sentence")).toContainText("of Ravi Raja in Goa");
  await floor(page, "results");
  await page.locator(".grid a").first().click();
  await page.waitForURL("**/photo/**");
  await expect(page.locator(".facts")).toContainText("Ravi Raja");
  await floor(page, "photo");
  await page.click("button:has-text('About this photo')");
  await expect(page.getByRole("heading", { name: "Who" })).toBeVisible();
  await expect(page.locator(".about")).toContainText("Ravi Raja");
  await floor(page, "photo, about");
  await page.click("text=Back to photos");
  await expect(page.locator(".sentence")).toContainText("Ravi Raja");
  await page.fill("#q", "1990s");
  await page.click("button:has-text('Search')");
  await expect(page.locator(".sentence")).toContainText("from the 1990s");
});

test("a person, then a year: one tap narrows a person's photos to a year", async ({ page }) => {
  await signIn(page);
  await page.goto("/find");
  await page.click(".chip:has-text('Meera Shah')");
  await expect(page.locator(".sentence")).toContainText("of Meera Shah");
  const years = page.locator("[aria-label='Years'] a.chip:not(.turn):visible");
  await expect(years.first()).toBeVisible();
  await floor(page, "person then year");
  let year = (await years.first().innerText()).trim();
  if (year.endsWith("s")) {
    // many years arrive as decades first; a decade then offers its own years
    await years.first().click();
    await expect(page.locator(".sentence")).toContainText(`of Meera Shah from the ${year}`);
    await expect(page.locator(`[aria-label='Years'] a[aria-current='true']`)).toHaveCount(0);
    year = (await years.first().innerText()).trim();
    expect(year).toMatch(/^\d{4}$/);
  }
  await years.first().click();
  await expect(page.locator(".sentence")).toContainText(`of Meera Shah from ${year}`);
  await expect(page.locator(`[aria-label='Years'] a[aria-current='true']`)).toHaveText(year);
  // every photo shown is that person's, from that year
  const truth = await (await page.request.get("/api/search?q=" + encodeURIComponent(`Meera Shah ${year}`))).json();
  expect(truth.total).toBeGreaterThan(0);
  for (const c of truth.cards) expect(c.year).toBe(Number(year));
  await page.click("[aria-label='Years'] a:has-text('All years')");
  await expect(page.locator(".sentence")).not.toContainText(" from ");
});

test("a year, then a person: one tap narrows a decade to one person", async ({ page }) => {
  await signIn(page);
  await page.goto("/find?show=years");
  await page.locator(".fit a.chip:has-text('2000s')").click();
  await expect(page.locator(".sentence")).toContainText("from the 2000s");
  const people = page.locator("[aria-label='Who is in these photos'] a.chip:not(.turn):visible");
  await expect(people.first()).toBeVisible();
  await floor(page, "year then person");
  const who = (await people.first().innerText()).trim();
  await people.first().click();
  await expect(page.locator(".sentence")).toContainText(`of ${who} from the 2000s`);
  // and the years row now offers that decade's years for that person
  await expect(page.locator("[aria-label='Years'] a:has-text('All years')")).toBeVisible();
});

test("a second search shows its own photos, never the last search's", async ({ page }) => {
  await signIn(page);
  await page.goto("/find?q=Asha%20Raja");
  await expect(page.locator(".grid a").first()).toBeVisible();
  await page.fill("#q", "Meera Shah");
  await page.click("button:has-text('Search')");
  await expect(page.locator(".sentence")).toContainText("of Meera Shah");
  // the photos themselves, not the links (the links take the new words either way)
  const shown = await page.locator(".grid a").evaluateAll((as) =>
    as.map((a) => decodeURIComponent((a.getAttribute("href") || "").split("/photo/")[1]?.split("?")[0] || "")));
  const truth = await (await page.request.get("/api/search?q=" + encodeURIComponent("Meera Shah"))).json();
  expect(shown.length).toBeGreaterThan(0);
  expect(shown).toEqual(truth.cards.map((c: { hash: string }) => c.hash));
  // and a search that finds nothing shows no photos at all
  await page.fill("#q", "1871");
  await page.click("button:has-text('Search')");
  await expect(page.locator(".sentence")).toContainText("Nothing found");
  await expect(page.locator(".grid a")).toHaveCount(0);
});

test("tapping a person's face finds their photos", async ({ page }) => {
  await signIn(page);
  await page.goto("/find");
  await page.click(".chip:has-text('Meera Shah')");
  await expect(page.locator(".sentence")).toContainText("of Meera Shah");
});

test("Who is this: a strong match is a yes/no, and the name lands in the database", async ({ page }) => {
  await signIn(page);
  await page.goto("/help");
  await expect(page.getByText("Is this Ravi Raja?")).toBeVisible();
  await floor(page, "who-is-this");
  await page.click("button:has-text('No')");
  await expect(page.getByRole("heading", { name: "Who is this?" })).toBeVisible();
  await floor(page, "choose");
  await page.click("button:has-text('Someone else')");
  await page.fill("#nm", "Nani");
  await page.click("button:has-text('Save this name')");
  await expect(page.getByText("means different people")).toBeVisible();
  await page.fill("#nm", "Kamala Raja");
  await page.click("button:has-text('Save this name')");
  await expect(page.getByText("now say")).toBeVisible();
  await floor(page, "celebration");
  // the thank-you shows at the tap; the answer lands a moment later
  await expect.poll(async () => [...await db`select who, scope, field, value, status from answers where field = 'person'`]).toEqual([{ who: "grandma", scope: "cluster", field: "person", value: "Kamala Raja", status: "new" }]);
  // instantly searchable, before any pull or re-seed
  await page.goto("/find?q=Kamala");
  await expect(page.locator(".sentence")).toContainText("of Kamala Raja");
});

test("the next face is already there: no blank Finding screen between faces", async ({ page }) => {
  await cleanSlate();
  await signIn(page);
  await page.goto("/help");
  await expect(page.getByText("Is this Ravi Raja?")).toBeVisible();
  await page.click("button:has-text('Yes!')");
  await expect(page.getByText("now say")).toBeVisible();
  await page.waitForLoadState("networkidle");          // the next face, fetched while this one was answered
  await page.evaluate(() => {
    (window as unknown as { blank: boolean }).blank = false;
    new MutationObserver(() => {
      if (document.body.textContent?.includes("Finding a face")) (window as unknown as { blank: boolean }).blank = true;
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  });
  await page.click("button:has-text('Next face')");
  await expect(page.getByText(/Is this |Who is this\?|People said different names/).first()).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { blank: boolean }).blank)).toBe(false);
});

test("Undo really takes the answer back", async ({ page }) => {
  await signIn(page, "Grandpa");
  await page.goto("/help");
  await page.locator("button.chip").first().click();
  await expect(page.getByText("now say")).toBeVisible();
  await page.click(".undo button:has-text('Undo')");
  await expect(page.getByRole("heading", { name: "Who is this?" })).toBeVisible();
  const [r] = await db`select status from answers where who = 'grandpa' order by at desc limit 1`;
  expect(r.status).toBe("undone");
});

test("I don't know is mine alone - it does not decline the face for everyone", async ({ page }) => {
  await signIn(page, "Auntie Meera");
  await page.goto("/help");
  const before = await db`select count(*)::int n from answers`;
  await page.click("button:has-text(\"I don't know\")");
  await expect.poll(async () => (await db`select who from skips`).map((r) => r.who)).toContain("auntie meera");
  const after = await db`select count(*)::int n from answers`;
  expect(after[0].n).toBe(before[0].n);
});

test("Where and when: a place for the whole day, then roughly what year", async ({ page }) => {
  await signIn(page);
  await page.goto("/story");
  await expect(page.getByText("Where was this taken?")).toBeVisible();
  await floor(page, "where");
  await page.click("button:has-text('Somewhere else')");
  await page.fill("#pl", "Nainital");
  await page.click("button:has-text('Save this place')");
  const day = page.getByText(/Also label the \d+ other/);
  await expect(day.or(page.getByText("Roughly what year?")).or(page.getByText("Thank you!"))).toBeVisible();
  if (await day.isVisible()) {
    await floor(page, "day");
    await page.click("button:has-text('Yes, all of them')");
  }
  await expect.poll(async () => (await db`select 1 from answers where field = 'place'`).length).toBe(1);
  const rows = await db`select field, value, array_length(hashes, 1) n from answers where field = 'place'`;
  expect(rows[0]).toMatchObject({ field: "place", value: "Nainital" });
  const placed = await db`select count(*)::int n from photos where family_place = 'Nainital'`;   // the family's place (0012)
  expect(placed[0].n).toBe(rows[0].n);
  if (await page.getByText("Roughly what year?").isVisible().catch(() => false)) {
    await floor(page, "decade");
    await page.click("button:has-text('1980s')");
    await page.click("button:has-text('1987')");
    await expect.poll(async () => (await db`select value from answers where field = 'approx_year'`).map((r) => r.value)).toEqual(["1987"]);
  }
});

test("a video judged whole plays, streamed in pieces; any other shows its still and says why", async ({ page, request }) => {
  await signIn(page);
  const ok = "0".repeat(63) + "8";
  const piece = 3.5 * 1024 * 1024;
  await page.goto(`/photo/${ok}`);
  const v = page.locator(".frame video");
  await expect(v).toBeVisible();
  await expect(page.locator(".caption")).toContainText("A video");
  await floor(page, "video");
  // the phone's own player reads it through the route, and it plays
  await expect.poll(() => v.evaluate((el: HTMLVideoElement) => el.readyState)).toBeGreaterThanOrEqual(1);
  expect(await v.evaluate((el: HTMLVideoElement) => Math.round(el.duration))).toBe(8);
  expect(await v.evaluate((el: HTMLVideoElement) => el.autoplay || !el.paused)).toBe(false);   // nothing plays by itself
  await v.evaluate((el: HTMLVideoElement) => { el.muted = true; return el.play(); });
  await expect.poll(() => v.evaluate((el: HTMLVideoElement) => el.currentTime)).toBeGreaterThan(1);
  // never more than one piece at a time, each saying where it sits in the whole
  const first = await page.request.get(`/video/${ok}`, { headers: { range: "bytes=0-" } });
  expect(first.status()).toBe(206);
  const total = Number(first.headers()["content-range"].split("/")[1]);
  expect(total).toBeGreaterThan(piece);
  expect(first.headers()["content-range"]).toBe(`bytes 0-${piece - 1}/${total}`);
  expect((await first.body()).length).toBe(piece);
  const last = await page.request.get(`/video/${ok}`, { headers: { range: `bytes=${total - 100}-` } });
  expect([last.status(), (await last.body()).length]).toEqual([206, 100]);
  expect((await page.request.get(`/video/${ok}`, { headers: { range: `bytes=${total}-` } })).status()).toBe(416);
  // not judged yet, and a format no phone plays: the still, the reason, and nothing streamed
  for (const [h, says] of [["0".repeat(62) + "15", "isn't ready to play yet"], ["0".repeat(62) + "22", "can't play on this phone"]]) {
    await page.goto(`/photo/${h}`);
    await expect(page.locator(".frame img")).toBeVisible();
    await expect(page.locator(".frame video")).toHaveCount(0);
    await expect(page.locator(".caption")).toContainText("A still from a video");
    await page.click("button:has-text('About this video')");
    await expect(page.locator(".about-text")).toContainText(says);
    expect((await page.request.get(`/video/${h}`, { headers: { range: "bytes=0-" } })).status()).toBe(404);
  }
  // signed out: nothing; hidden: nothing, even judged clear
  expect((await request.get(`/video/${ok}`, { headers: { range: "bytes=0-" } })).status()).toBe(401);
  await db`update photos set hidden = true, hidden_by = 'test' where hash = ${ok}`;
  try {
    expect((await page.request.get(`/video/${ok}`, { headers: { range: "bytes=0-" } })).status()).toBe(404);
  } finally {
    await db`update photos set hidden = false, hidden_by = null where hash = ${ok}`;
  }
});

test("a video the phone cannot play after all puts its still back", async ({ page }) => {
  await signIn(page);
  await page.route("**/video/**", (r) => r.fulfill({ status: 206, contentType: "video/mp4",
    headers: { "content-range": "bytes 0-9/10" }, body: "not video!" }));
  await page.goto(`/photo/${"0".repeat(63)}8`);
  await expect(page.locator(".frame img")).toBeVisible();
  await expect(page.locator(".frame video")).toHaveCount(0);
  await page.click("button:has-text('About this video')");
  await expect(page.locator(".about-text")).toContainText("can't play on this phone");
});

test("a wrong year is put right in two taps, with the photos from the same day, and wins everywhere", async ({ page }) => {
  // the file says 2 February 2020 (the day a batch was scanned); the family knows better
  const h = "0".repeat(63) + "2";
  const [{ day_key }] = await db`select day_key from photos where hash = ${h}`;
  const rows = await db`select hash, day_key from photos where media = 'photo' and hash <> ${h} and family_when is null
    order by hash limit 3 offset 20`;
  const batch = rows.map((r) => r.hash as string);
  await db`update photos set day_key = ${day_key} where hash = any(${batch})`;
  try {
    await signIn(page);
    await page.goto(`/photo/${h}`);
    const when = page.locator("button.fact-when");
    await expect(when).toContainText("Change");
    await floor(page, "photo, the year");
    await when.click();
    await expect(page.getByText("When was this photo taken?")).toBeVisible();
    await floor(page, "photo, which decade");
    await page.click("button:has-text('1980s')");
    await expect(page.getByText("Which year in the 1980s?")).toBeVisible();
    await expect(page.locator("[aria-label='Years'] button:has-text('1989')")).toBeVisible();   // all ten, no turning
    await floor(page, "photo, which year");
    await page.click("[aria-label='Years'] button:has-text('1987')");
    await expect(page.getByText("Change the 3 other photos")).toBeVisible();
    await floor(page, "photo, the same day too");
    await page.click("button:has-text('Yes, all 4')");
    await expect(page.getByText("Saved: 1987 for 4 photos")).toBeVisible();
    await expect(when).toContainText("1987");
    await expect.poll(async () => (await db`select count(*)::int n from photos where family_when = '1987'
      and hash = any(${[h, ...batch]})`)[0].n).toBe(4);
    // the family's year wins over the file's everywhere: the photo, the grid, the search
    await page.goto(`/photo/${h}`);
    await expect(page.locator("button.fact-when")).toContainText("1987");
    await page.goto("/find?q=1987");
    await expect(page.locator(".sentence")).toContainText("1987");
    await expect(page.locator(`.grid a[href*='${h}'] .badge`)).toHaveText("1987");
    // and Undo puts it back as it was
    await page.goto(`/photo/${h}`);
    await page.locator("button.fact-when").click();
    await page.click("button:has-text('1990s')");
    await page.click("[aria-label='Years'] button:has-text('1991')");      // the others already have a year: not asked again
    await expect(page.locator("button.fact-when")).toContainText("1991");
    await page.click(".undo button:has-text('Undo')");
    await expect(page.locator("button.fact-when")).toContainText("1987");
    await expect.poll(async () => (await db`select family_when from photos where hash = ${h}`)[0].family_when).toBe("1987");
  } finally {
    await db`update answers set status = 'undone' where field = 'approx_year' and hashes && ${[h, ...batch]}`;
    await db`update photos set family_when = null where hash = any(${[h, ...batch]})`;
    for (const r of rows) await db`update photos set day_key = ${r.day_key} where hash = ${r.hash}`;
  }
});

test("who and where are put right from the photo itself, and win everywhere", async ({ page }) => {
  await signIn(page);
  await page.goto("/find?q=Asha%20Raja");
  const href = (await page.locator(".grid a").first().getAttribute("href"))!;
  const h = decodeURIComponent(href.split("/photo/")[1].split("?")[0]);
  const [{ place: was }] = await db`select coalesce(family_place, place) place from photos where hash = ${h}`;
  try {
    await page.goto(href);
    await floor(page, "photo, who where when");
    // WHO: a wrong name comes off this photograph only
    await page.click("button.fact-who");
    await expect(page.getByText("Who is in this photo?")).toBeVisible();
    await floor(page, "photo, who is in it");
    await page.click("[aria-label='Take Asha Raja off this photo']");
    await expect(page.getByText("Taken off: Asha Raja")).toBeVisible();
    await expect(page.locator(".fact-who")).not.toContainText("Asha Raja");
    await expect.poll(async () => (await db`select name from photo_people where hash = ${h}`).map((r) => r.name)).not.toContain("Asha Raja");
    const asha = await (await page.request.get("/api/search?q=" + encodeURIComponent("Asha Raja"))).json();
    expect(asha.cards.map((c: { hash: string }) => c.hash)).not.toContain(h);
    // ... and someone missing goes on, spelled the way the family spells them
    await page.click("button.fact-who");
    await page.click("button:has-text('Add someone')");
    await page.fill("#who-add", "sam kapor");
    await page.click("button:has-text('Save this name')");
    await expect(page.getByText("Did you mean Sam Kapoor?")).toBeVisible();
    await floor(page, "photo, add someone, did you mean");
    await page.click("[aria-label='Names we already know'] button:has-text('Sam Kapoor')");
    await expect(page.getByText("Added: Sam Kapoor")).toBeVisible();
    const sam = await (await page.request.get("/api/search?q=" + encodeURIComponent("Sam Kapoor"))).json();
    expect(sam.cards.map((c: { hash: string }) => c.hash)).toContain(h);
    // WHERE: the family's place wins over the library's, in search too
    await page.click("button.fact-where");
    await expect(page.getByText("Where was this photo taken?")).toBeVisible();
    await floor(page, "photo, where");
    await page.click("button:has-text('Somewhere else')");
    await page.fill("#pl", "Nainital");
    await page.click("button:has-text('Save this place')");
    const all = page.getByRole("button", { name: /Yes, all/ });
    if (await all.isVisible().catch(() => false)) await page.click("button:has-text('Just this one')");
    await expect(page.locator(".fact-where")).toContainText("Nainital");
    const found = await (await page.request.get("/api/search?q=Nainital")).json();
    expect(found.cards.map((c: { hash: string }) => c.hash)).toContain(h);
    await page.click(".undo button:has-text('Undo')");
    await expect(page.locator(".fact-where")).toContainText(String(was ?? "Not known"));
    await expect.poll(async () => (await db`select family_place from photos where hash = ${h}`)[0].family_place).toBe(null);
  } finally {
    await db`update answers set status = 'undone' where hashes && ${[h]} and field in ('place', 'in_photo', 'not_in_photo')`;
    await db`update photos set family_place = null where hash = ${h}`;
  }
});

test("Previous and Next turn through the photos a search found", async ({ page }) => {
  await signIn(page);
  await page.goto("/find?q=Asha%20Raja");
  const hrefs = await page.locator(".grid a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!));
  expect(hrefs.length).toBeGreaterThan(2);
  await page.goto(hrefs[1]);
  const prev = page.getByRole("link", { name: "Previous photo" }), next = page.getByRole("link", { name: "Next photo" });
  await expect(next).toBeVisible();
  await floor(page, "photo, previous and next");
  await next.click();
  await page.waitForURL((u) => u.pathname === new URL(hrefs[2], "http://x").pathname);
  await prev.click();
  await page.waitForURL((u) => u.pathname === new URL(hrefs[1], "http://x").pathname);
  await page.getByRole("link", { name: "Previous photo" }).click();
  await page.waitForURL((u) => u.pathname === new URL(hrefs[0], "http://x").pathname);
  await expect(page.getByRole("button", { name: "Previous photo" })).toBeDisabled();       // the first has none before it
  await page.click("text=Back to photos");
  await expect(page.locator(".sentence")).toContainText("Asha Raja");
});

test("Hide this photo removes it for everyone at once", async ({ page }) => {
  await signIn(page);
  await page.goto("/find?q=Asha%20Raja");
  await page.locator(".grid a").first().click();
  await page.waitForURL("**/photo/**");
  const hash = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  await page.click("button:has-text('About this photo')");
  await page.click("text=This photo shouldn't be here");
  await page.click("button:has-text('Yes, hide it')");
  await expect(page.getByText("hidden for everyone")).toBeVisible();
  const r = await page.request.get(`/img/t/${encodeURIComponent(hash)}`);
  expect(r.status()).toBe(404);
  await db`update photos set hidden = false where hash = ${hash}`;
});

test("an answer sent twice is stored once", async ({ page }) => {
  await signIn(page);
  const id = "11111111-2222-4333-8444-555555555555";
  const [g] = await db`select group_id from queue order by rank desc limit 1`;
  const body = { id, kind: "mixed", group: g.group_id, value: "mixed" };
  for (let i = 0; i < 3; i++) expect((await page.request.post("/api/answers", { data: body })).ok()).toBe(true);
  const n = await db`select count(*)::int n from answers where id = ${id}`;
  expect(n[0].n).toBe(1);
});

// ---- Krish, 2026-10-05: skipped faces come back around; nobody's answer
// overrides anybody else's; a misspelling is caught.

async function person(browser: import("@playwright/test").Browser, name: string) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await signIn(page, name);
  return page;
}
const cleanSlate = async () => {
  await db`delete from answers where scope = 'cluster'`;
  await db`delete from skips`;
};
const named = async (g: string) =>
  (await db`select name, answered, contested from group_names where group_id = ${g}`)[0];

test("two people who disagree are both kept, and the next person settles it", async ({ browser }) => {
  await cleanSlate();
  // a family gathering: two phones open on the same face at the same time
  const grandma = await person(browser, "Grandma");
  const grandpa = await person(browser, "Grandpa");
  await grandma.goto("/help");
  await grandpa.goto("/help");
  await expect(grandma.getByText("Is this Ravi Raja?")).toBeVisible();
  await expect(grandpa.getByText("Is this Ravi Raja?")).toBeVisible();
  await grandma.click("button:has-text('Yes!')");
  await expect(grandma.getByText("now say")).toBeVisible();
  await expect.poll(async () => (await db`select 1 from answers where scope = 'cluster'`).length).toBe(1);
  await grandpa.click("button:has-text('No')");
  await grandpa.click("button:has-text('Someone else')");
  await grandpa.fill("#nm", "Kamala Raja");
  await grandpa.click("button:has-text('Save this name')");
  await expect(grandpa.getByText("now say")).toBeVisible();
  // neither answer replaced the other
  await expect.poll(async () => [...await db`select who, value, status from answers where scope = 'cluster' order by at`]).toEqual([{ who: "grandma", value: "Ravi Raja", status: "new" }, { who: "grandpa", value: "Kamala Raja", status: "new" }]);
  // one each: the first given shows, and the face is still asked of everyone else
  expect(await named("g7")).toEqual({ name: "Ravi Raja", answered: false, contested: true });

  const meera = await person(browser, "Auntie Meera");
  await meera.goto("/help");
  await expect(meera.getByText("People said different names")).toBeVisible();
  await expect(meera.getByText(/^Is this /)).toHaveCount(0);            // the question is which, not a yes/no
  await floor(meera, "contested");
  await meera.click("[aria-label='Names people have given'] button:has-text('Kamala Raja')");
  await expect(meera.getByText("now say")).toBeVisible();
  await expect.poll(() => named("g7")).toEqual({ name: "Kamala Raja", answered: true, contested: false });
  // the two who already answered are not asked it again
  expect((await grandma.request.get("/api/face/next").then((r) => r.json())).group).toBe("g8");
  for (const p of [grandma, grandpa, meera]) await p.context().close();
});

test("changing your own mind replaces only your own answer", async ({ page }) => {
  await cleanSlate();
  await signIn(page);
  const post = (value: string) => page.request.post("/api/answers", {
    data: { id: crypto.randomUUID(), kind: "person", group: "g8", value } });
  expect((await post("Meera Shah")).ok()).toBe(true);
  expect((await post("Asha Raja")).ok()).toBe(true);
  expect((await post("Asha Raja")).ok()).toBe(true);
  const votes = await db`select who, value from group_votes where group_id = 'g8'`;
  expect(votes).toEqual([{ who: "grandma", value: "Asha Raja" }]);    // one person, one vote
  expect(await named("g8")).toEqual({ name: "Asha Raja", answered: true, contested: false });
});

test("I don't know comes back around: after the rest, and never for anyone else", async ({ page, browser }) => {
  await cleanSlate();
  await signIn(page, "Grandpa");
  await page.goto("/help");
  await expect(page.getByText("Is this Ravi Raja?")).toBeVisible();      // g7 first
  await page.click("button:has-text(\"I don't know\")");
  await expect(page.getByRole("heading", { name: "Who is this?" })).toBeVisible();   // g8 next
  await page.click("button:has-text(\"I don't know\")");
  await expect(page.getByText("That's every face for now")).toBeVisible();
  await floor(page, "every face seen");
  await page.click("button:has-text('Look at those again')");
  // the first one they did not know comes back first
  await expect(page.getByText("Is this Ravi Raja?")).toBeVisible();
  // a later visit: the faces they skipped wait behind anything they have not seen
  await db`insert into queue (group_id, rank, photo_count, hero_face, sample_faces, suggestions)
           select 'g6', 5, photo_count, hero_face, '{}', '[]'::jsonb from queue where group_id = 'g8'`;
  await db`update clusters set name = null where group_id = 'g6'`;
  await page.goto("/help");
  await expect(page.getByRole("heading", { name: "Who is this?" })).toBeVisible();
  await expect(page.getByText("Is this Ravi Raja?")).toHaveCount(0);
  await expect.poll(async () => (await page.request.get("/api/face/next").then((r) => r.json())).group).toBe("g6");
  // Grandma never skipped anything: her queue is untouched by Grandpa's
  const grandma = await person(browser, "Grandma");
  expect((await grandma.request.get("/api/face/next").then((r) => r.json())).group).toBe("g7");
  await grandma.context().close();
  await db`delete from queue where group_id = 'g6'`;
  await db`update clusters set name = 'Sam Kapoor' where group_id = 'g6'`;
});

test("a misspelt name is caught, and the same name typed differently is the same name", async ({ page }) => {
  await cleanSlate();
  await signIn(page);
  await page.goto("/help");
  await page.click("button:has-text('No')");
  await page.click("button:has-text('Someone else')");
  await page.fill("#nm", "Meera Sha");
  await page.click("button:has-text('Save this name')");
  await expect(page.getByText("Did you mean Meera Shah?")).toBeVisible();
  await floor(page, "did you mean");
  await page.click("[aria-label='Names we already know'] button:has-text('Meera Shah')");
  await expect(page.getByText("now say")).toBeVisible();
  await expect.poll(async () => (await db`select 1 from answers where scope = 'cluster'`).length).toBe(1);
  // case and spacing are not spelling: stored as the family already spells it
  const r = await page.request.post("/api/answers", { data: { id: crypto.randomUUID(), kind: "person", group: "g8", value: "  ASHA   raja " } });
  expect(r.ok()).toBe(true);
  const vals = await db`select value from answers where scope = 'cluster' order by at`;
  expect(vals.map((v) => v.value)).toEqual(["Meera Shah", "Asha Raja"]);
  // a name that is nobody's near miss is saved as typed, and "no" keeps what was typed
  await cleanSlate();
  await page.goto("/help");
  await page.click("button:has-text('No')");
  await page.click("button:has-text('Someone else')");
  await page.fill("#nm", "Dev Sha");
  await page.click("button:has-text('Save this name')");
  await page.click("button:has-text('No, save')");
  await expect(page.getByText("now say")).toBeVisible();
  await expect.poll(async () => (await db`select value from answers where scope = 'cluster'`).map((r) => r.value)).toEqual(["Dev Sha"]);
});

test("places: a misspelling is caught, a second opinion is counted not written over, the family's place wins and the library's is kept", async ({ page, browser }) => {
  await db`delete from answers where scope = 'file'`;
  await db`delete from skips`;
  await db`update photos set family_place = null`;
  await db`update photos set place = null where place = 'Nainital' or place = 'Naini Tal'`;
  await signIn(page);
  await page.goto("/story");
  await expect(page.getByText("Where was this taken?")).toBeVisible();
  await page.click("button:has-text('Somewhere else')");
  await page.fill("#pl", "Bri ghton");
  await page.click("button:has-text('Save this place')");
  await expect(page.getByText("Did you mean Brighton?")).toBeVisible();
  await page.click("[aria-label='Places we already know'] button:has-text('Brighton')");
  const day = page.getByText(/Also label the \d+ other/);
  await expect(day.or(page.getByText("Roughly what year?")).or(page.getByText("Thank you!"))).toBeVisible();
  if (await day.isVisible()) await page.click("button:has-text('Just this one')");
  await expect.poll(async () => (await db`select value from answers where field = 'place'`).map((r) => r.value)).toEqual(["Brighton"]);

  // one photo, three people: first answer shows; a different one is kept but does not replace it
  const [p] = await db`select hash from photos where place is null and visible and media = 'photo' limit 1`;
  const grandpa = await person(browser, "Grandpa");
  const meera = await person(browser, "Auntie Meera");
  const say = async (pg: typeof page, value: string, hash = p.hash as string) => {
    const id = crypto.randomUUID();
    expect((await pg.request.post("/api/answers", { data: { id, kind: "place", hashes: [hash], value } })).ok()).toBe(true);
    return id;
  };
  const place = async (hash = p.hash as string) => (await db`select coalesce(family_place, place) place from photos where hash = ${hash}`)[0].place;
  await say(page, "Goa");
  expect(await place()).toBe("Goa");
  await say(grandpa, "Mumbai");
  expect(await place()).toBe("Goa");                                     // a tie: the first given
  const third = await say(meera, "mumbai");
  expect(await place()).toBe("Mumbai");                                  // two to one, one spelling
  expect((await db`select count(*)::int n from answers where hashes @> array[${p.hash}]`)[0].n).toBe(3);
  // taking an answer back: the photo shows what the others' answers add up to
  expect((await meera.request.post("/api/answers/undo", { data: { id: third } })).ok()).toBe(true);
  expect(await place()).toBe("Goa");

  // a wrong library place is put right by the family (Krish, 2026-10-06), and the
  // library's own is kept underneath: take the answer back and it shows again
  const [lib] = await db`select hash from photos where place = 'Sydney' and visible and media = 'photo' limit 1`;
  const delhi = await say(grandpa, "Delhi", lib.hash);
  expect(await place(lib.hash)).toBe("Delhi");
  expect((await db`select place from photos where hash = ${lib.hash}`)[0].place).toBe("Sydney");
  expect((await grandpa.request.post("/api/answers/undo", { data: { id: delhi } })).ok()).toBe(true);
  expect(await place(lib.hash)).toBe("Sydney");
  for (const pg of [grandpa, meera]) await pg.context().close();
});

