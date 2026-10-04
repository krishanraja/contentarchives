import { describe, expect, it } from "vitest";
import { describe as sentence, parseQuery } from "../lib/search";

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
