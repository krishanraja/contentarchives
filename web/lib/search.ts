// Turning what a grandparent types into filters the index can answer.
// "Bharti in Goa 1998" -> person Bharti, place Goa, year 1998. Whatever is
// left ("at the beach") is ranked by meaning. The same split as
// embed_descriptions.py's --person / --place / --year.

export type Parsed = {
  people: string[];
  place: string | null;
  yearFrom: number | null;
  yearTo: number | null;
  rest: string;
};

const STOP = new Set(["photos", "photo", "pictures", "picture", "pics", "of",
  "in", "at", "from", "the", "with", "and", "show", "me", "find", "all", "a",
  "an", "on", "when", "was", "were", "my", "our"]);

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function parseQuery(q: string, people: string[], places: string[]): Parsed {
  let text = " " + (q || "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}\s'-]/gu, " ") + " ";
  const out: Parsed = { people: [], place: null, yearFrom: null, yearTo: null, rest: "" };

  // longest names first, so "Asha Raja" wins over "Asha"
  for (const name of [...people].sort((a, b) => b.length - a.length)) {
    const re = new RegExp(`(?<=\\s)${escapeRe(name.toLowerCase())}(?='?s?\\s)`, "u");
    if (re.test(text)) {
      out.people.push(name);
      text = text.replace(re, " ");
    }
  }
  // A first name (or any one part of a name) on its own: "Asha" means Asha
  // Raja when she is the only Asha we know. Two Ashas and it stays a word.
  const byPart = new Map<string, string[]>();
  for (const name of people) {
    for (const part of name.toLowerCase().split(/\s+/)) {
      if (part.length < 3) continue;
      byPart.set(part, [...(byPart.get(part) || []), name]);
    }
  }
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const w = word.replace(/'s$/, "");
    const hit = byPart.get(w);
    if (hit && hit.length === 1 && !out.people.includes(hit[0])) {
      out.people.push(hit[0]);
      text = text.replace(new RegExp(`(?<=\\s)${escapeRe(word)}(?=\\s)`, "u"), " ");
    }
  }
  for (const place of [...places].sort((a, b) => b.length - a.length)) {
    const re = new RegExp(`(?<=\\s)${escapeRe(place.toLowerCase())}(?=\\s)`, "u");
    if (place.length >= 3 && re.test(text)) {
      out.place = place;
      text = text.replace(re, " ");
      break;
    }
  }
  // 1998 / 1980s / 80s / '80s
  const decade = text.match(/(?<=\s)(?:(1[89]|20)(\d)0|'?(\d)0)s(?=\s)/);
  if (decade) {
    const y = decade[1] ? Number(decade[1] + decade[2] + "0")
      : (Number(decade[3]) >= 3 ? 1900 : 2000) + Number(decade[3]) * 10;
    out.yearFrom = y; out.yearTo = y + 9;
    text = text.replace(decade[0], " ");
  } else {
    const year = text.match(/(?<=\s)(18[5-9]\d|19\d\d|20\d\d)(?=\s)/);
    if (year) {
      out.yearFrom = out.yearTo = Number(year[1]);
      text = text.replace(year[0], " ");
    }
  }
  out.rest = text.split(/\s+/).filter((w) => w && !STOP.has(w)).join(" ");
  return out;
}

// One plain sentence a person can read: "48 photos of Bharti in Goa, 1998".
export function describe(p: Parsed, total: number, mode = "filters"): string {
  // A meaning search ranks EVERY photo by how close it is, so its "total" is the
  // whole library - "22,752 photos that look like beach" told a grandparent
  // nothing. It says what it is doing instead: closest first.
  const ranked = mode === "meaning" && !!p.rest;
  const n = ranked ? "Photos" : total === 1 ? "1 photo" : `${total.toLocaleString("en-GB")} photos`;
  const parts = [n];
  if (p.people.length) parts.push("of " + p.people.join(" and "));
  if (p.rest) parts.push(ranked ? `that look most like “${p.rest}”` : `that look like “${p.rest}”`);
  if (p.place) parts.push("in " + p.place);
  if (p.yearFrom) parts.push(p.yearFrom === p.yearTo ? `from ${p.yearFrom}` : `from the ${p.yearFrom}s`);
  return parts.join(" ") + (ranked ? ", closest first" : "");
}
