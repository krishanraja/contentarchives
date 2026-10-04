import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { cloudHold, nudityHold } from "../lib/share";

// The SAME table tests/test_app_share_set.py reads: the Python seed and this
// cloud rule must give the same answer for every case, or one of them is wrong.
const table = JSON.parse(readFileSync(path.join(__dirname, "../../stages/13_app/nudity_cases.json"), "utf8"));

describe("the nudity rule (shared table with Python)", () => {
  for (const c of table.cases) {
    it(`${c.name} -> ${c.shared ? "shared" : "held"}`, () => {
      expect(nudityHold(c.sensitivity, c.sens, c.released) === "").toBe(c.shared);
    });
  }
});

describe("cloud files", () => {
  it("never releases adult nudity - the cloud has no human release", () => {
    expect(cloudHold("photo", { kind: "photo", sensitivity: "none", nudity: "partial", subject_age: "adult", sexual: "no" })).not.toBe("");
  });
  it("holds a screenshot", () => {
    expect(cloudHold("photo", { kind: "screenshot", sensitivity: "none", nudity: "none" })).not.toBe("");
  });
  it("shares an ordinary photograph", () => {
    expect(cloudHold("photo", { kind: "photo", sensitivity: "none", nudity: "none", subject_age: "adult", sexual: "no" })).toBe("");
  });
  it("holds a file the model said nothing about", () => {
    expect(cloudHold("photo", { kind: "photo" })).not.toBe("");
  });
});
