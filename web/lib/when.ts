// How the family's answer about when reads: "1987", or "The 1980s". Plain code,
// used on the server (the photo page) and on the phone (after an answer).
export const whenLabel = (v: string) => (/s$/.test(v) ? `The ${v}` : v);

export const dayText = (d: Date | string) =>
  new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

// When a photograph was taken, in words. What the family said wins over the
// date in the file (migration 0011): a scan or a copy carries the day it was
// made, not the day the picture was.
export function whenText(p: { family_when: string | null; year: number | null; approx_year: string | null; taken_at: Date | string | null }) {
  if (p.family_when) return whenLabel(p.family_when);
  if (p.taken_at) return dayText(p.taken_at);
  if (p.year) return String(p.year);
  if (p.approx_year) return `About ${p.approx_year}`;
  return null;
}
