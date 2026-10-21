import { test, expect } from "@playwright/test";
import { ADMIN, db, floor, signIn } from "./helpers";

// Fix a spelling (Krish, 2026-10-21): a name saved two
// ways is put right once, by the owner, as answers - never as an edit.
const WRONG = "Dev Sah", RIGHT = "Dev Shah";

test.describe.configure({ mode: "serial" });

test.beforeEach(async () => {
  // a photo the library lists under the wrong spelling, and the name on Find
  await db`update photos set people = array_replace(people, ${RIGHT}, ${WRONG})
    where hash = (select hash from photos where ${RIGHT} = any(people) and visible order by hash limit 1)`;
  await db`insert into people (name, cover_face, photo_count) values (${WRONG}, null, 1) on conflict do nothing`;
  await db`delete from spelling_verdicts`;
  await db`select refresh_photo_people()`;
});

test.afterEach(async () => {
  await db`update photos set people = array_replace(people, ${WRONG}, ${RIGHT})`;
  await db`delete from answers where who = 'owner'`;
  await db`delete from people where name = ${WRONG}`;
  await db`delete from spelling_verdicts`;
  await db`select refresh_photo_people()`;
});

test("only the owner can open it", async ({ page }) => {
  await signIn(page, "Grandma");
  const r = await page.goto("/spelling");
  expect(r?.status()).toBe(404);
  const post = await page.request.post("/api/spelling", { form: { op: "same", a: WRONG, b: RIGHT, keep: WRONG } });
  expect(post.status()).toBe(404);
  expect((await db`select count(*)::int n from answers where value = ${WRONG}`)[0].n).toBe(0);
});

test("the owner keeps one spelling, and it is put right everywhere as answers", async ({ page }) => {
  await signIn(page, "Owner", ADMIN);
  await page.goto("/spelling");
  await expect(page.locator("h2")).toHaveText("Are these the same person?");
  await expect(page.locator(".spell-side b")).toHaveCount(2);
  expect((await page.locator(".spell-side b").allInnerTexts()).sort()).toEqual([WRONG, RIGHT].sort());
  await floor(page, "fix a spelling");
  await page.click(`button:has-text('Same person: call them ${RIGHT}')`);
  await expect(page.locator(".notice")).toContainText(`${WRONG} is now ${RIGHT}`);
  // the library's own listing is outvoted on that photo, by the owner's answers
  const rows = await db`select field, value, cardinality(hashes) n from answers where who = 'owner' order by field`;
  expect(rows.map((r) => [r.field, r.value, r.n])).toEqual([["in_photo", RIGHT, 1], ["not_in_photo", WRONG, 1]]);
  expect((await db`select count(*)::int n from photo_people_mv where name = ${WRONG}`)[0].n).toBe(0);
  expect((await db`select count(*)::int n from people where name = ${WRONG}`)[0].n).toBe(0);
  expect((await db`select verdict, kept from spelling_verdicts`)[0]).toMatchObject({ verdict: "same", kept: RIGHT });
  // Find no longer offers the wrong spelling
  await page.goto("/find?show=people");
  await expect(page.locator(`.fit a.chip:has-text('${WRONG}')`)).toHaveCount(0);
});

test("two different people: nothing is changed, and the pair is not asked again", async ({ page }) => {
  await signIn(page, "Owner", ADMIN);
  await page.goto("/spelling");
  await page.click("button:has-text('No, two different people')");
  await expect(page.locator(".spell-side b")).not.toHaveText([WRONG, RIGHT]);
  expect((await db`select count(*)::int n from answers where who = 'owner'`)[0].n).toBe(0);
  expect((await db`select verdict from spelling_verdicts`)[0].verdict).toBe("different");
});
