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
  await page.fill("#code", "  Archives ");
  await page.click("button:has-text('Open')");
  await page.waitForURL("**/who");
  await floor(page, "who");
  await page.click("button:has-text('Grandma')");
  await page.waitForURL((u) => u.pathname === "/");
  await expect(page.getByRole("heading", { name: "Hello, Grandma!" })).toBeVisible();
  await floor(page, "home");
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
  await expect(page.getByRole("heading", { name: "Who" })).toBeVisible();
  await expect(page.locator(".card")).toContainText("Ravi Raja");
  await floor(page, "photo");
  await page.click("text=Back to photos");
  await expect(page.locator(".sentence")).toContainText("Ravi Raja");
  await page.fill("#q", "1990s");
  await page.click("button:has-text('Search')");
  await expect(page.locator(".sentence")).toContainText("from the 1990s");
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
  const rows = await db`select who, scope, field, value, status from answers where field = 'person'`;
  expect(rows).toEqual([{ who: "grandma", scope: "cluster", field: "person", value: "Kamala Raja", status: "new" }]);
  // instantly searchable, before any pull or re-seed
  await page.goto("/find?q=Kamala");
  await expect(page.locator(".sentence")).toContainText("of Kamala Raja");
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
  const placed = await db`select count(*)::int n from photos where place = 'Nainital'`;
  expect(placed[0].n).toBe(rows[0].n);
  if (await page.getByText("Roughly what year?").isVisible().catch(() => false)) {
    await floor(page, "decade");
    await page.click("button:has-text('1980s')");
    await page.click("button:has-text('1987')");
    await expect.poll(async () => (await db`select value from answers where field = 'approx_year'`).map((r) => r.value)).toEqual(["1987"]);
  }
});

test("Hide this photo removes it for everyone at once", async ({ page }) => {
  await signIn(page);
  await page.goto("/find?q=Asha%20Raja");
  await page.locator(".grid a").first().click();
  await page.waitForURL("**/photo/**");
  const hash = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
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

test.afterAll(async () => { await db.end(); });
