import { describe, expect, it } from "vitest";
import { validate } from "../lib/data";

const id = "3f2b6c1e-8a4d-4c2e-9b7a-1d2e3f4a5b6c";
describe("an answer is checked before it is stored", () => {
  it("accepts a name for a face group", () => expect(validate({ id, kind: "person", group: "g1", value: "Asha Raja" })).toBeNull());
  it("refuses a question as a name", () => {
    expect(validate({ id, kind: "person", group: "g1", value: "?" })).not.toBeNull();
    expect(validate({ id, kind: "person", group: "g1", value: "for Bharti" })).not.toBeNull();
  });
  it("refuses a sentence", () => expect(validate({ id, kind: "person", group: "g1", value: "x".repeat(61) })).not.toBeNull());
  it("refuses an answer without a phone-made id", () => expect(validate({ id: "1", kind: "person", group: "g1", value: "A" })).not.toBeNull());
  it("accepts a year or a decade, nothing else", () => {
    expect(validate({ id, kind: "year", hashes: ["h"], value: "1987" })).toBeNull();
    expect(validate({ id, kind: "year", hashes: ["h"], value: "1980s" })).toBeNull();
    expect(validate({ id, kind: "year", hashes: ["h"], value: "ages ago" })).not.toBeNull();
  });
  it("needs photos for a place", () => expect(validate({ id, kind: "place", hashes: [], value: "Goa" })).not.toBeNull());
});
