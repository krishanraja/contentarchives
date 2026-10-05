import { describe, expect, it } from "vitest";
import { close, distance, exact, fold } from "../lib/spelling";

const PEOPLE = ["Asha Raja", "Ashvin Raja", "Usha Raja", "Isha Patel", "Meera Shah", "Dev Shah"];
const PLACES = ["Nainital", "Goa", "Victoria Falls", "Coogee"];

describe("what is not a spelling difference", () => {
  it("case, spacing, punctuation and Unicode form fold away", () => {
    expect(fold("  asha   RAJA. ")).toBe("asha raja");
    expect(fold("Asha-Raja")).toBe("asha raja");
    expect(fold("Ａｓｈａ Raja")).toBe("asha raja");          // full-width letters (NFKC)
    expect(exact("asha raja", PEOPLE)).toBe("Asha Raja");
  });
  it("a name in another script keeps its letters", () => {
    expect(fold("आशा राजा")).not.toBe("");
  });
});

describe("did you mean", () => {
  it("a slip finds the name it was meant to be", () => {
    expect(close("Ashwin Raja", PEOPLE)).toContain("Ashvin Raja");
    expect(close("Usha Rja", PEOPLE)[0]).toBe("Usha Raja");
    expect(close("Meera Sha", PEOPLE)[0]).toBe("Meera Shah");
    expect(close("Naintal", PLACES)).toEqual(["Nainital"]);
  });
  it("a swapped pair of letters is one slip", () => {
    expect(distance("asha", "ahsa")).toBe(1);
    expect(close("Ahsa Raja", PEOPLE)[0]).toBe("Asha Raja");
  });
  it("a first name alone points to the full name", () => {
    expect(close("Ashvin", PEOPLE)).toContain("Ashvin Raja");
  });
  it("an exact name (however it is typed) needs no question", () => {
    expect(close("ASHA  RAJA", PEOPLE)).toEqual([]);
  });
  it("a different name is offered, never merged: the person decides", () => {
    // Isha and Asha may be two people: close() only ever SUGGESTS
    expect(exact("Isha Raja", PEOPLE)).toBeNull();
  });
  it("something unlike anything known finds nothing", () => {
    expect(close("Kamala Devi", PEOPLE)).toEqual([]);
    expect(close("Paris", PLACES)).toEqual([]);
  });
});
