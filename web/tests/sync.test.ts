import { afterAll, beforeAll, describe, expect, it } from "vitest";
import postgres from "postgres";
import { readFileSync } from "node:fs";
import path from "node:path";
import { syncDrive, type Deps } from "../lib/sync";
import type { DriveFile } from "../lib/drive";

// Against a real Postgres with the real migration. Skipped where none is set.
const ADMIN = process.env.TEST_PG_ADMIN || "postgres://postgres:pw@127.0.0.1:54329/postgres";
const NAME = "arch_sync_test";
let db: postgres.Sql; let ok = true;

beforeAll(async () => {
  try {
    const admin = postgres(ADMIN, { max: 1 });
    await admin.unsafe(`drop database if exists ${NAME}`);
    await admin.unsafe(`create database ${NAME}`);
    await admin.end();
    db = postgres(ADMIN.replace(/\/[^/]*$/, "/" + NAME), { max: 2, prepare: false, onnotice: () => {} });
    const dir = path.join(__dirname, "../supabase");
    await db.unsafe(readFileSync(path.join(dir, "test/shim.sql"), "utf8"));
    await db.unsafe(readFileSync(path.join(dir, "migrations/0001_archives.sql"), "utf8"));
  } catch (e) {
    // A database test that cannot reach its database must FAIL, not pass
    // vacuously: a run with Postgres down once reported these six as green.
    ok = false;
    if (!process.env.SKIP_PG) throw new Error("no Postgres for the sync tests (set SKIP_PG=1 to skip on purpose): " + e);
  }
});
afterAll(async () => { if (db) await db.end(); });

const f = (id: string, rel: string, md5 = "", mime = "image/jpeg"): DriveFile =>
  ({ id, name: rel.split("/").pop()!, mimeType: mime, md5Checksum: md5 || undefined, relPath: rel });
const deps = (files: DriveFile[], verdicts: Record<string, Record<string, any>> = {}): Deps => ({
  list: async () => files,
  image: async () => Buffer.from("jpeg"),
  classify: async () => { throw new Error("set per test"); },
  embed: null,
  budget: 50,
  ...(Object.keys(verdicts).length ? { classify: async () => verdicts.next } : {}),
});

describe("the daily Drive sync", () => {
  it("binds seeded photos to Drive by md5, then by path", async () => {
    if (!ok) return;
    await db`insert into photos (hash, rel_path, md5) values
      ('h1', 'Media/Communal/2001/a.jpg', 'aaa'), ('h2', 'Media/Communal/2002/b.jpg', null)`;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d2", "Media/Communal/2002/b.jpg")];
    const r = await syncDrive(db, { ...deps(files), classify: null });
    expect(r.bound).toBe(2);
    const rows = await db`select hash, drive_id from photos order by hash`;
    expect(rows.map((x) => [x.hash, x.drive_id])).toEqual([["h1", "d1"], ["h2", "d2"]]);
  });

  it("before the first seed, nothing is classified, whatever is on Drive", async () => {
    if (!ok) return;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d2", "Media/Communal/2002/b.jpg"),
      f("dz", "Media/Communal/2020/z.jpg")];
    const r = await syncDrive(db, { ...deps(files), classify: async () => { throw new Error("must not be asked"); } });
    expect([r.seeded, r.added, r.waiting, r.removed]).toEqual([false, 0, 1, 0]);
    await db`insert into snapshots (kind) values ('seed')`;
  });

  it("without a classifier key, new files WAIT - nothing is shown unjudged", async () => {
    if (!ok) return;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d2", "Media/Communal/2002/b.jpg"),
      f("d3", "Media/Communal/2020/new.jpg")];
    const r = await syncDrive(db, { ...deps(files), classify: null });
    expect(r.waiting).toBe(1);
    expect((await db`select count(*)::int n from photos`)[0].n).toBe(2);
  });

  it("adds an ordinary new photo and holds an adult nude one", async () => {
    if (!ok) return;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d2", "Media/Communal/2002/b.jpg"),
      f("d3", "Media/Communal/2020/new.jpg"), f("d4", "Media/Communal/2020/bad.jpg")];
    const v: Record<string, Record<string, any>> = {
      d3: { kind: "photo", sensitivity: "none", nudity: "none", subject_age: "adult", sexual: "no", description: "Two people at a picnic." },
      d4: { kind: "photo", sensitivity: "none", nudity: "full", subject_age: "adult", sexual: "no", description: "x" },
    };
    let current = "";
    const r = await syncDrive(db, { ...deps(files), image: async (x) => { current = x.id; return Buffer.from("j"); },
      classify: async () => v[current] });
    expect([r.added, r.held]).toEqual([1, 1]);
    const [p] = await db`select hash, year, description, source from photos where drive_id = 'd3'`;
    expect(p).toMatchObject({ hash: "drive:d3", year: 2020, source: "cloud" });
    expect((await db`select count(*)::int n from photos where drive_id = 'd4'`)[0].n).toBe(0);
    expect((await db`select reason from held where drive_id = 'd4'`)[0].reason).toMatch(/adult/);
  });

  it("a second run with nothing new changes nothing", async () => {
    if (!ok) return;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d2", "Media/Communal/2002/b.jpg"),
      f("d3", "Media/Communal/2020/new.jpg"), f("d4", "Media/Communal/2020/bad.jpg")];
    const r = await syncDrive(db, { ...deps(files), classify: async () => { throw new Error("must not be asked"); } });
    expect([r.bound, r.added, r.held, r.removed, r.waiting]).toEqual([0, 0, 0, 0, 0]);
  });

  it("a file deleted from Drive leaves the app", async () => {
    if (!ok) return;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d3", "Media/Communal/2020/new.jpg")];
    const r = await syncDrive(db, { ...deps(files), classify: null });
    expect(r.removed).toBe(1);
    expect((await db`select drive_id from photos order by drive_id`).map((x) => x.drive_id)).toEqual(["d1", "d3"]);
  });

  it("a seeded row takes its file over from a row the cloud added by itself", async () => {
    if (!ok) return;
    await db`insert into photos (hash, drive_id, rel_path, source) values ('drive:d9', 'd9', 'Media/Communal/2021/x.jpg', 'cloud')`;
    await db`insert into photos (hash, rel_path, md5, source) values ('h9', 'Media/Communal/2021/x.jpg', 'f9', 'seed')`;
    const files = [f("d1", "Media/Communal/2001/renamed.jpg", "AAA"), f("d3", "Media/Communal/2020/new.jpg"),
      f("d9", "Media/Communal/2021/x.jpg", "F9")];
    const r = await syncDrive(db, { ...deps(files), classify: null });
    expect([r.bound, r.replaced]).toEqual([1, 1]);
    expect((await db`select hash from photos where drive_id = 'd9'`).map((x) => x.hash)).toEqual(["h9"]);
  });

  it("a broken listing removes NOTHING", async () => {
    if (!ok) return;
    const many = Array.from({ length: 30 }, (_, i) => ({ hash: `m${i}`, drive_id: `m${i}` }));
    await db`insert into photos ${db(many)}`;
    const r = await syncDrive(db, { ...deps([]), classify: null });
    expect(r.refusedRemoval).toMatch(/refusing/);
    expect((await db`select count(*)::int n from photos`)[0].n).toBe(33);
  });
});
