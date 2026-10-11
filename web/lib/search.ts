// Turning what a grandparent types into filters the index can answer.
// "Bharti in Goa 1998" -> person Bharti, place Goa, year 1998. Whatever is
// left ("at the beach") is ranked by meaning. The same split as
// embed_descriptions.py's --person / --place / --year.

export type Media = "photo" | "video";

export type Parsed = {
  people: string[];
  place: string | null;
  yearFrom: number | null;
  yearTo: number | null;
  media: Media | null;              // null: photos and videos both
  rest: string;
};

// The four facts a search can be narrowed by, and the words. Every link on the
// Find page is one of these changed (lib/search compose / findHref).
export type Pick = "who" | "where" | "when" | "say";
export const PICKS: Pick[] = ["who", "where", "when", "say"];

export function asMedia(v: unknown): Media | null {
  return v === "photo" || v === "video" ? v : null;
}

const STOP = new Set(["photos", "photo", "pictures", "picture", "pics", "of",
  "in", "at", "from", "the", "with", "and", "show", "me", "find", "all", "a",
  "an", "on", "when", "was", "were", "my", "our"]);

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function parseQuery(q: string, people: string[], places: string[]): Parsed {
  let text = " " + (q || "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}\s'-]/gu, " ") + " ";
  const out: Parsed = { people: [], place: null, yearFrom: null, yearTo: null, media: null, rest: "" };

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
  // "videos of Asha": the word is the type, not something to look like.
  // "photos" stays a filler word - "photos of Asha" means everything of her.
  const video = /(?<=\s)(?:videos?|clips?|movies?|home movies?)(?=\s)/g;
  if (video.test(text)) {
    out.media = "video";
    text = text.replace(video, " ");
  }
  out.rest = text.split(/\s+/).filter((w) => w && !STOP.has(w)).join(" ");
  return out;
}

// The noun for what a search can return: "photos", "videos", or both.
export function noun(media: Media | null, n: number | null = null): string {
  const one = n === 1;
  if (media === "video") return one ? "video" : "videos";
  if (media === "photo") return one ? "photo" : "photos";
  return one ? "photo or video" : "photos and videos";
}

// One plain sentence a person can read: "48 photos of Bharti in Goa, 1998".
export function describe(p: Parsed, total: number, mode = "filters", present?: { photo: number; video: number }): string {
  // A meaning search ranks EVERY photo by how close it is, so its "total" is the
  // whole library - "22,752 photos that look like beach" told a grandparent
  // nothing. It says what it is doing instead: closest first.
  // With no type chosen it names what is actually there: only photographs
  // found says "photos", only videos "videos", a mix "photos and videos".
  const media = p.media ?? (present && !present.video ? "photo" : present && !present.photo ? "video" : null);
  const ranked = mode === "meaning" && !!p.rest;
  const what = noun(media, ranked ? null : total);
  const n = ranked ? what[0].toUpperCase() + what.slice(1) : `${total.toLocaleString("en-GB")} ${what}`;
  const parts = [n];
  if (p.people.length) parts.push("of " + p.people.join(" and "));
  if (p.rest) parts.push(ranked ? `that look most like “${p.rest}”` : `that look like “${p.rest}”`);
  if (p.place) parts.push("in " + p.place);
  if (p.yearFrom) parts.push(p.yearFrom === p.yearTo ? `from ${p.yearFrom}` : `from the ${p.yearFrom}s`);
  return parts.join(" ") + (ranked ? ", closest first" : "");
}

// A year chosen, as the words the parser reads back: "1998" or "1990s".
export function yearWord(p: Parsed): string | null {
  if (p.yearFrom === null) return null;
  return p.yearFrom === p.yearTo ? String(p.yearFrom) : `${p.yearFrom}s`;
}

export type Change = { people?: string[]; place?: string | null; year?: string | null; rest?: string; media?: Media | null };

// A search with one part changed, in the words the parser reads back. The
// type is not in the words (a "photos" word means nothing): it rides as
// ?type=, so every link carries it and a person can set it at any point.
export function compose(p: Parsed, change: Change = {}): string {
  const people = change.people ?? p.people;
  const place = change.place !== undefined ? change.place : p.place;
  const year = change.year !== undefined ? change.year : yearWord(p);
  const rest = change.rest !== undefined ? change.rest : p.rest;
  return [...people, place, year, rest].filter(Boolean).join(" ").trim();
}

// The link for a search with one part changed, and optionally a panel open.
export function findHref(p: Parsed, change: Change = {}, pick: Pick | null = null): string {
  const q = compose(p, change);
  const media = change.media !== undefined ? change.media : p.media;
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (media) qs.set("type", media);
  if (pick) qs.set("pick", pick);
  const s = qs.toString();
  return s ? `/find?${s}` : "/find";
}

// Year counts as the chips to offer: a long span as decades first (a 15-year
// span would take seven "More" taps otherwise); inside a chosen decade, or
// beside a chosen year, that decade's years. Newest first.
export function foldYears(rows: { y: number; n: number }[], yearFrom: number | null): { label: string; n: number }[] {
  const years = [...rows].sort((a, b) => b.y - a.y);
  if (yearFrom !== null) {
    const within = Math.floor(yearFrom / 10) * 10;
    return years.filter((x) => x.y >= within && x.y <= within + 9).map((x) => ({ label: String(x.y), n: x.n }));
  }
  if (years.length > 6 && new Set(years.map((x) => Math.floor(x.y / 10))).size > 1) {
    const by = new Map<number, number>();
    for (const x of years) { const d = Math.floor(x.y / 10) * 10; by.set(d, (by.get(d) || 0) + x.n); }
    return [...by].sort((a, b) => b[0] - a[0]).map(([d, n]) => ({ label: `${d}s`, n }));
  }
  return years.map((x) => ({ label: String(x.y), n: x.n }));
}

// "1:23" for a video's length; null when it is not known yet.
export function clock(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || !(seconds >= 0)) return null;
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

// The list the photo screen turns through with Previous and Next, as the
// results screen left it on this phone: one per search and type.
export const listKey = (q: string, type: Media | null) => `photos:${q}|${type || ""}`;
