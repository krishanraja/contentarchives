import { describe, expect, it } from "vitest";
import { describe as sentence, parseQuery } from "../lib/search";
import type { Parsed } from "../lib/search";

const PEOPLE = ["Asha Raja", "Ravi Raja", "Meera Shah", "Asha Patel"];
const PLACES = ["Goa", "Lake District", "Delhi"];

describe("parseQuery", () => {
  it("finds a full name, a place and a year", () => {
    const p = parseQuery("Meera Shah in Goa 1998", PEOPLE, PLACES);
    expect(p.people).toEqual(["Meera Shah"]);
    expect(p.place).toBe("Goa");
    expect([p.yearFrom, p.yearTo]).toEqual([1998, 1998]);
    expect(p.rest).toBe("");
  });
  it("treats a unique first name as that person", () => {
    expect(parseQuery("Ravi at the beach", PEOPLE, PLACES).people).toEqual(["Ravi Raja"]);
  });
  it("leaves an ambiguous first name as a word", () => {
    const p = parseQuery("asha", PEOPLE, PLACES);
    expect(p.people).toEqual([]);
    expect(p.rest).toBe("asha");
  });
  it("understands decades however they are written", () => {
    expect(parseQuery("1980s", PEOPLE, PLACES)).toMatchObject({ yearFrom: 1980, yearTo: 1989 });
    expect(parseQuery("the 80s", PEOPLE, PLACES)).toMatchObject({ yearFrom: 1980, yearTo: 1989 });
    // the Find page's example is "<most photographed decade>s": it must read as a decade alone
    expect(parseQuery("2010s", PEOPLE, PLACES)).toMatchObject({ yearFrom: 2010, yearTo: 2019, rest: "" });
    expect(parseQuery("'90s", PEOPLE, PLACES)).toMatchObject({ yearFrom: 1990, yearTo: 1999 });
    expect(parseQuery("00s", PEOPLE, PLACES)).toMatchObject({ yearFrom: 2000, yearTo: 2009 });
  });
  it("keeps the meaning words and drops filler", () => {
    expect(parseQuery("show me photos of a birthday party in the Lake District", PEOPLE, PLACES))
      .toMatchObject({ place: "Lake District", rest: "birthday party" });
  });
  it("handles a possessive name", () => {
    expect(parseQuery("Ravi's wedding", PEOPLE, PLACES)).toMatchObject({ people: ["Ravi Raja"], rest: "wedding" });
  });
  it("says what it found in one plain sentence", () => {
    const p = parseQuery("Meera Shah Goa 1998", PEOPLE, PLACES);
    expect(sentence(p, 48)).toBe("48 photos of Meera Shah in Goa from 1998");
    expect(sentence(parseQuery("1980s", PEOPLE, PLACES), 1)).toBe("1 photo from the 1980s");
  });
});

describe("the sentence above the results", () => {
  const p = (o: Partial<Parsed>): Parsed => ({ people: [], place: null, yearFrom: null, yearTo: null, rest: "", ...o });
  it("a meaning search never claims the whole library looks like the words", () => {
    const s = sentence(p({ rest: "beach" }), 22752, "meaning");
    expect(s).toBe("Photos that look most like “beach”, closest first");
    expect(s).not.toContain("22,752");
  });
  it("a meaning search inside a filter says both", () => {
    expect(sentence(p({ rest: "wedding", yearFrom: 1998, yearTo: 1998 }), 300, "meaning"))
      .toBe("Photos that look most like “wedding” from 1998, closest first");
  });
  it("a filter search still counts what it found", () => {
    expect(sentence(p({ people: ["Asha Raja"] }), 48, "filters")).toBe("48 photos of Asha Raja");
    expect(sentence(p({ yearFrom: 1990, yearTo: 1999 }), 1, "filters")).toBe("1 photo from the 1990s");
  });
  it("a word search (no meaning) counts its matches", () => {
    expect(sentence(p({ rest: "goa" }), 12, "words")).toBe("12 photos that look like “goa”");
  });
});
