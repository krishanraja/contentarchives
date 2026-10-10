import { describe, expect, it, vi } from "vitest";
import { memo } from "../lib/memo";
import { spellAs } from "../lib/spelling";

// A per-save query must not scan the library (learning 80): the known names
// are kept for a minute, and a save checks only the answers given since.
describe("the known names, kept for a minute", () => {
  it("a second read within the minute does not load again", async () => {
    let t = 0;
    const load = vi.fn(async () => ["Asha Raja"]);
    const m = memo(load, 60_000, () => t);
    await m.get();
    t = 59_999;
    await m.get();
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("after the minute it loads again", async () => {
    let t = 0;
    const load = vi.fn(async () => ["Asha Raja"]);
    const m = memo(load, 60_000, () => t);
    await m.get();
    t = 60_000;
    await m.get();
    expect(load).toHaveBeenCalledTimes(2);
  });
  it("readers arriving together share one load", async () => {
    const load = vi.fn(async () => ["Asha Raja"]);
    const m = memo(load, 60_000);
    await Promise.all([m.get(), m.get(), m.get()]);
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("cleared after a new name is saved, the next read loads it", async () => {
    let names = ["Asha Raja"];
    const m = memo(async () => names, 60_000, () => 0);
    await m.get();
    names = ["Asha Raja", "Dev Shah"];
    m.clear();
    expect(await m.get()).toContain("Dev Shah");
  });
  it("a failed load is never kept", async () => {
    let fail = true;
    const m = memo(async () => { if (fail) throw new Error("db down"); return ["Asha Raja"]; }, 60_000, () => 0);
    await expect(m.get()).rejects.toThrow("db down");
    fail = false;
    expect(await m.get()).toEqual(["Asha Raja"]);
  });
});

describe("the spelling a saved answer takes", () => {
  const KNOWN = ["Asha Raja", "Meera Shah"];
  it("a known name, however typed, never asks the database", async () => {
    const recent = vi.fn(async () => []);
    expect(await spellAs("asha  RAJA", KNOWN, recent)).toBe("Asha Raja");
    expect(recent).not.toHaveBeenCalled();
  });
  it("a name another phone gave a minute ago, missing from the kept list, is still that name", async () => {
    expect(await spellAs("dev shah", KNOWN, async () => ["Dev Shah"])).toBe("Dev Shah");
  });
  it("a name nobody has given is kept as typed", async () => {
    expect(await spellAs("Kamala Devi", KNOWN, async () => ["Dev Shah"])).toBe("Kamala Devi");
  });
});
