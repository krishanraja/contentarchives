import { describe, expect, it } from "vitest";
import { keys, nearPairs } from "@/lib/respell";
import { addPerson } from "@/lib/search";

const P = (...xs: [string, number][]) => xs.map(([name, n]) => ({ name, n }));

describe("fix a spelling: the pairs put to the owner", () => {
  it("finds one name spelled two ways", () => {
    expect(nearPairs(P(["Zora", 34], ["Zara", 10], ["Ravi Raja", 1918]), new Set())).toEqual([["Zora", "Zara"]]);
  });
  it("asks each pair once, whichever name it was found from", () => {
    const pairs = nearPairs(P(["Kavita", 39], ["Kavitta", 32]), new Set());
    expect(pairs).toHaveLength(1);
  });
  it("never asks a pair already decided, either way round", () => {
    const decided = new Set([keys("Zara", "Zora").join("|")]);
    expect(nearPairs(P(["Zora", 34], ["Zara", 10]), decided)).toEqual([]);
  });
  it("puts the closest spellings first", () => {
    const pairs = nearPairs(P(["Zora", 34], ["Zara", 10], ["Asha", 6985], ["Asha Raja", 2]), new Set());
    expect(pairs[0]).toEqual(["Zora", "Zara"]);
  });
  it("leaves names that differ only in case or spacing alone: those are one name already", () => {
    expect(nearPairs(P(["Asha Raja", 5], ["asha  raja", 1]), new Set())).toEqual([]);
  });
  it("keys a pair the same whichever way round, smaller first", () => {
    expect(keys("Zara", "Zora")).toEqual(["zara", "zora"]);
    expect(keys("Zora", "Zara")).toEqual(["zara", "zora"]);
  });
});

describe("add a second person: one wording for the button and the panel", () => {
  it("counts on from the people chosen", () => {
    expect(addPerson(["Asha Raja"])).toBe("Add a second person");
    expect(addPerson(["Asha Raja", "Ravi Raja"])).toBe("Add a third person");
    expect(addPerson(["A", "B", "C"])).toBe("Add a fourth person");
    expect(addPerson(["A", "B", "C", "D"])).toBe("Add another person");
  });
});
