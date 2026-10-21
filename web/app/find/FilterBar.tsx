import Go from "@/components/Go";
import Fit from "@/components/Fit";
import { ABROAD, addPerson, findHref, UK, yearWord, type Parsed, type Pick } from "@/lib/search";

// What the search is narrowed by, and what it could be narrowed by next
// (Krish, 2026-10-11: start with a name, then the time, the place or say what
// you are looking for; start with a place, then the person...). Whatever was
// chosen first, every fact is offered the same way, so nothing depends on
// where a search started:
//   four buttons that are always there - Who, Where, When, Say - each opening
//   its choices in place of the photos (marked when that fact is chosen);
//   a pill for each fact chosen: tap it to change it, ✕ takes it off;
//   and, once someone is chosen, "+ Add a second person" under the pills.
// All of them are real links, so they work before the script arrives.
const WORDS: Record<Pick, string> = { who: "Who", where: "Where", when: "When", say: "Say" };

export default function FilterBar({ p, open }: { p: Parsed; open: Pick | null }) {
  const year = yearWord(p);
  const set: Record<Pick, boolean> = { who: p.people.length > 0, where: !!p.place || !!p.country, when: !!year, say: !!p.rest };
  const countryText = p.country === UK ? "In the UK" : p.country === ABROAD ? "Abroad" : p.country;
  const ask: Record<Pick, string> = {
    who: p.people.length ? addPerson(p.people) : "Choose who is in them",
    where: p.place || countryText ? `Where: ${[p.place, countryText].filter(Boolean).join(", ")}. Change the place` : "Choose where",
    when: year ? `When: ${year}. Change the time` : "Choose when",
    say: p.rest ? `Words: ${p.rest}. Change the words` : "Say or type what is in them",
  };
  const pill = (key: string, pick: Pick, text: string, off: string, offLabel: string) => (
    <span key={key} className={open === pick ? "pill open" : "pill"}>
      <Go className="pill-go" href={findHref(p, {}, pick)} aria-label={`${text}: change`}>{text}</Go>
      <Go className="pill-off" href={off} aria-label={offLabel}>✕</Go>
    </span>
  );
  const pills = [
    ...p.people.map((n) => pill("who:" + n, "who", n,
      findHref(p, { people: p.people.filter((x) => x !== n) }), `Take ${n} off`)),
    // on a short screen the offer rides in this row instead of one of its own
    ...(p.people.length && !open ? [
      <span key="who:add" className="pill add">
        <Go className="pill-go" href={findHref(p, {}, "who")}>+ {addPerson(p.people)}</Go>
      </span>] : []),
    ...(p.place ? [pill("where", "where", p.place, findHref(p, { place: null }), `Take ${p.place} off`)] : []),
    ...(countryText ? [pill("country", "where", countryText, findHref(p, { country: null }), `Anywhere, not just ${p.country === UK ? "in the UK" : p.country === ABROAD ? "abroad" : countryText}`)] : []),
    ...(year ? [pill("when", "when", year, findHref(p, { year: null }), `Any time, not just ${year}`)] : []),
    ...(p.rest ? [pill("say", "say", `“${p.rest}”`, findHref(p, { rest: "" }), `Take the words “${p.rest}” off`)] : []),
  ];
  return (
    <>
      <nav className="dims" aria-label="Narrow it down">
        {(Object.keys(WORDS) as Pick[]).map((k) => (
          <Go key={k} className={set[k] ? "btn small set" : "btn small"} aria-label={ask[k]}
            href={open === k ? findHref(p) : findHref(p, {}, k)} aria-current={open === k ? "page" : undefined}>
            {WORDS[k]}
          </Go>
        ))}
      </nav>
      {pills.length > 0 && <Fit key={findHref(p)} one label="Chosen" more="More">{pills}</Fit>}
      {/* once someone is chosen, the next person is offered right under them,
          with the photos, rather than left behind the Who button (Krish,
          2026-10-21). Its own row: in the pills' one row it went behind "More"
          on a 360-390px phone. A screen too short for the row (a phone on its
          side) shows the copy in the pills' row instead (globals.css). */}
      {p.people.length > 0 && !open &&
        <Go className="btn small add-person" href={findHref(p, {}, "who")}>+ {addPerson(p.people)}</Go>}
    </>
  );
}
