import { describe, expect, it } from "vitest";
import { clock, compose, describe as sentence, findHref, foldYears, parseQuery } from "../lib/search";
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
    expect(sentence(p, 48)).toBe("48 photos and videos of Meera Shah in Goa from 1998");
    expect(sentence(p, 48, "filters", { photo: 48, video: 0 })).toBe("48 photos of Meera Shah in Goa from 1998");
    expect(sentence(p, 2, "filters", { photo: 0, video: 2 })).toBe("2 videos of Meera Shah in Goa from 1998");
    expect(sentence(parseQuery("1980s", PEOPLE, PLACES), 1, "filters", { photo: 1, video: 0 })).toBe("1 photo from the 1980s");
  });
});

describe("the sentence above the results", () => {
  const p = (o: Partial<Parsed>): Parsed => ({ people: [], place: null, country: null, yearFrom: null, yearTo: null, media: null, rest: "", ...o });
  it("a meaning search never claims the whole library looks like the words", () => {
    const s = sentence(p({ rest: "beach" }), 22752, "meaning");
    expect(s).toBe("Photos and videos that look most like “beach”, closest first");
    expect(s).not.toContain("22,752");
  });
  it("a meaning search inside a filter says both", () => {
    expect(sentence(p({ rest: "wedding", yearFrom: 1998, yearTo: 1998, media: "photo" }), 300, "meaning"))
      .toBe("Photos that look most like “wedding” from 1998, closest first");
  });
  it("a filter search still counts what it found", () => {
    expect(sentence(p({ people: ["Asha Raja"] }), 48, "filters")).toBe("48 photos and videos of Asha Raja");
    expect(sentence(p({ yearFrom: 1990, yearTo: 1999, media: "photo" }), 1, "filters")).toBe("1 photo from the 1990s");
  });
  it("a word search (no meaning) counts its matches", () => {
    expect(sentence(p({ rest: "goa", media: "photo" }), 12, "words")).toBe("12 photos that look like “goa”");
  });
});

describe("photos or videos (Krish, 2026-10-11)", () => {
  it("reads the word video as the type, not as something to look like", () => {
    expect(parseQuery("videos of Asha Raja in Goa", PEOPLE, PLACES))
      .toMatchObject({ people: ["Asha Raja"], place: "Goa", media: "video", rest: "" });
    expect(parseQuery("home movies from the 80s", PEOPLE, PLACES))
      .toMatchObject({ media: "video", yearFrom: 1980, rest: "" });
    expect(parseQuery("a clip of the wedding", PEOPLE, PLACES)).toMatchObject({ media: "video", rest: "wedding" });
  });
  it("leaves 'photos of' meaning everything", () => {
    expect(parseQuery("photos of Ravi", PEOPLE, PLACES).media).toBeNull();
  });
  it("names what it found: photos, videos, or both", () => {
    const b = parseQuery("Meera Shah", PEOPLE, PLACES);
    expect(sentence({ ...b, media: "video" }, 3)).toBe("3 videos of Meera Shah");
    expect(sentence({ ...b, media: "video" }, 1)).toBe("1 video of Meera Shah");
    expect(sentence({ ...b, media: "photo" }, 12)).toBe("12 photos of Meera Shah");
    expect(sentence({ ...b, media: null }, 12)).toBe("12 photos and videos of Meera Shah");
    expect(sentence({ ...b, media: "video", rest: "cake" }, 900, "meaning"))
      .toBe("Videos of Meera Shah that look most like “cake”, closest first");
  });
  it("a video's length reads like a clock", () => {
    expect(clock(8)).toBe("0:08");
    expect(clock(83)).toBe("1:23");
    expect(clock(3725)).toBe("1:02:05");
    expect(clock(null)).toBeNull();
  });
});

describe("narrowing from wherever a search starts", () => {
  const people = parseQuery("Asha Raja", PEOPLE, PLACES);
  const place = parseQuery("Goa", PEOPLE, PLACES);
  it("every change is words the parser reads back to the same search", () => {
    const changes = [
      { people: ["Asha Raja", "Ravi Raja"] }, { place: "Lake District" }, { year: "1998" }, { year: "1990s" },
      { rest: "birthday party" }, { people: [] as string[], place: "Delhi", year: "2001" },
    ];
    for (const start of [people, place]) {
      for (const c of changes) {
        const back = parseQuery(compose(start, c), PEOPLE, PLACES);
        const want = { ...start, media: null, ...{
          people: c.people ?? start.people, place: c.place !== undefined ? c.place : start.place,
          rest: c.rest ?? start.rest } };
        expect(back.people).toEqual(want.people);
        expect(back.place).toEqual(want.place);
        expect(back.rest).toEqual(want.rest);
        if (c.year) expect(back.yearFrom).toBe(Number(c.year.slice(0, 4)));
      }
    }
  });
  it("from a person: add a place, a time, a type, words - and take any off", () => {
    expect(findHref(people, { place: "Goa" })).toBe("/find?q=Asha+Raja+Goa");
    expect(findHref(people, { media: "video" })).toBe("/find?q=Asha+Raja&type=video");
    expect(findHref({ ...people, media: "video" }, { year: "1990s" }, "who")).toBe("/find?q=Asha+Raja+1990s&type=video&pick=who");
    expect(findHref({ ...people, place: "Goa" }, { people: [] })).toBe("/find?q=Goa");
    expect(findHref(people, { people: [] })).toBe("/find");
  });
  it("from a place: add a person, and the type stays", () => {
    expect(findHref({ ...place, media: "photo" }, { people: ["Meera Shah"] })).toBe("/find?q=Meera+Shah+Goa&type=photo");
  });
});

describe("the years offered", () => {
  const rows = [1984, 1987, 1991, 1998, 1999, 2003, 2011].map((y, i) => ({ y, n: i + 1 }));
  it("a long span comes as decades, newest first", () => {
    expect(foldYears(rows, null)).toEqual([
      { label: "2010s", n: 7 }, { label: "2000s", n: 6 }, { label: "1990s", n: 3 + 4 + 5 }, { label: "1980s", n: 1 + 2 }]);
  });
  it("inside a decade, or beside a year, that decade's years", () => {
    expect(foldYears(rows, 1990).map((x) => x.label)).toEqual(["1999", "1998", "1991"]);
    expect(foldYears(rows, 1998).map((x) => x.label)).toEqual(["1999", "1998", "1991"]);
  });
  it("a short span comes as years", () => {
    expect(foldYears(rows.slice(0, 3), null).map((x) => x.label)).toEqual(["1991", "1987", "1984"]);
  });
});

describe("UK, abroad and countries (Krish, 2026-10-12: \"UK versus abroad, which would be handy\")", () => {
  const COUNTRIES = ["United Kingdom", "India", "Iceland"];
  const PL = [...PLACES, "Golden Temple, Amritsar, India", "India"];
  it("reads UK and abroad, in the words a person would type", () => {
    expect(parseQuery("Meera Shah in the UK", PEOPLE, PL, COUNTRIES).country).toBe("United Kingdom");
    expect(parseQuery("Meera Shah U.K. 1990s", PEOPLE, PL, COUNTRIES)).toMatchObject({ country: "United Kingdom", yearFrom: 1990 });
    expect(parseQuery("Meera Shah abroad", PEOPLE, PL, COUNTRIES)).toMatchObject({ country: "abroad", rest: "" });
    expect(parseQuery("overseas 2010s", PEOPLE, PL, COUNTRIES)).toMatchObject({ country: "abroad", yearFrom: 2010 });
  });
  it("a country's name is the whole country, but a place that names one stays that place", () => {
    expect(parseQuery("India", PEOPLE, PL, COUNTRIES)).toMatchObject({ country: "India", place: null });
    expect(parseQuery("Golden Temple, Amritsar, India", PEOPLE, PL, COUNTRIES))
      .toMatchObject({ place: "Golden Temple, Amritsar, India", country: null });
  });
  it("a chosen country rides in the link and reads back the same", () => {
    const p = parseQuery("Meera Shah Goa", PEOPLE, PL, COUNTRIES);
    for (const c of ["United Kingdom", "abroad", "India"]) {
      const href = findHref(p, { country: c, place: null });
      const q = new URLSearchParams(href.split("?")[1]).get("q") || "";
      expect(parseQuery(q, PEOPLE, PL, COUNTRIES)).toMatchObject({ people: ["Meera Shah"], country: c, place: null });
    }
  });
  it("the sentence says where", () => {
    expect(sentence(parseQuery("Meera Shah abroad", PEOPLE, PL, COUNTRIES), 12, "filters", { photo: 12, video: 0 }))
      .toBe("12 photos of Meera Shah abroad");
    expect(sentence(parseQuery("Meera Shah UK", PEOPLE, PL, COUNTRIES), 3, "filters", { photo: 3, video: 0 }))
      .toBe("3 photos of Meera Shah in the UK");
  });
});

describe("a place with a comma in its name (it never matched before 2026-10-12)", () => {
  it("chosen from the list, it is found again in its own link", () => {
    const places = ["Blue Lagoon, Iceland", "Goa"];
    const p = parseQuery("Meera Shah", PEOPLE, places);
    const q = new URLSearchParams(findHref(p, { place: "Blue Lagoon, Iceland" }).split("?")[1]).get("q") || "";
    expect(parseQuery(q, PEOPLE, places)).toMatchObject({ people: ["Meera Shah"], place: "Blue Lagoon, Iceland", rest: "" });
  });
});

describe("the Find screen answers a tap at once (learning 81)", () => {
  it("every choice on the Find screen answers the tap at once: each is a Go, never a bare Link", async () => {
    const { readFileSync } = await import("node:fs");
    for (const f of ["FilterBar.tsx", "FacetPanel.tsx", "TypeSwitch.tsx"]) {
      const src = readFileSync(new URL(`../app/find/${f}`, import.meta.url), "utf8");
      expect(src, f).not.toMatch(/from "next\/link"/);
      expect(src, f).toMatch(/<Go /);
    }
    const go = readFileSync(new URL("../components/Go.tsx", import.meta.url), "utf8");
    expect(go).toMatch(/<Link prefetch/);
    expect(go).toMatch(/useLinkStatus/);
  });
});
