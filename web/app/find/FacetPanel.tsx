import Go from "@/components/Go";
import Fit from "@/components/Fit";
import Mic from "@/components/Mic";
import { ABROAD, addPerson, findHref, noun, UK, yearWord, type Parsed, type Pick } from "@/lib/search";
import type { Facets } from "@/lib/data";

// One fact to choose, in place of the photos (the screen never scrolls), each
// choice with how many it would give with everything else already chosen.
// "Done" goes back to the photos unchanged.
export default function FacetPanel({ p, pick, f }: { p: Parsed; pick: Pick; f: Facets }) {
  const n = (x: number) => <span className="n" aria-hidden="true">{x.toLocaleString("en-GB")}</span>;
  const what = noun(p.media);
  const done = <Go className="btn small sun done" href={findHref(p)}>Done</Go>;
  // in a list, "Done" is its first chip: no row of its own on a short screen
  const doneChip = <Go key="__done" className="chip turn done" href={findHref(p)}>✓ Done</Go>;
  if (pick === "say") {
    // a real GET form: what is said is read the same way as the search box,
    // so "Ravi at the beach" adds Ravi as a person and ranks by "beach"
    return (
      <section className="facet" aria-labelledby="facet-h">
        <div className="facet-top"><h2 id="facet-h" className="facet-h">What is in the {what}?</h2>{done}</div>
        <form className="searchrow" method="get" action="/find">
          {(() => { const base = findHref(p, { rest: "" }); const qs = new URLSearchParams(base.split("?")[1] || "");
            return <>
              <input type="hidden" name="q" value={qs.get("q") || ""} />
              {qs.get("type") && <input type="hidden" name="type" value={qs.get("type")!} />}
            </>; })()}
          <label className="sr" htmlFor="say">Say or type what is in them</label>
          <input id="say" name="say" className="field" type="search" defaultValue={p.rest}
            placeholder="a beach, a cake…" enterKeyHint="search" autoComplete="off" />
          <Mic target="say" />
          <button className="btn sun">Find</button>
        </form>
      </section>
    );
  }
  let title = "", chips: React.ReactNode[] = [];
  if (pick === "who") {
    // "Who else is in these?" read as a question about who they are; it is
    // the offer the button beside the names makes (Krish, 2026-10-21)
    title = p.people.length ? `${addPerson(p.people)} with ${p.people.join(" and ")}` : `Who is in the ${what}?`;
    chips = f.people.map((x) => (
      <Go key={x.name} className="chip" href={findHref(p, { people: [...p.people, x.name] })}
        aria-label={`${x.name}, ${x.n}`}>
        {x.cover && <img src={`/face/${encodeURIComponent(x.cover)}`} alt="" />}{x.name}{n(x.n)}
      </Go>
    ));
  } else if (pick === "where") {
    // First the country: in the UK, or abroad (Krish, 2026-10-12: "UK versus
    // abroad, which would be handy"), then the countries abroad, then places.
    // A country chosen replaces the place; a place is chosen within it.
    title = `Where were the ${what} taken?`;
    const uk = f.countries.find((c) => c.country === UK)?.n ?? 0;
    const away = f.countries.filter((c) => c.country !== UK);
    const abroad = away.reduce((t, c) => t + c.n, 0);
    const country = (c: string, word: string, count: number) => (
      <Go key={"c:" + c} className="chip" href={findHref(p, { country: c, place: null })}
        aria-label={`${word}, ${count}`} aria-current={p.country === c ? "true" : undefined}>{word}{n(count)}</Go>
    );
    chips = [
      ...(p.place || p.country ? [<Go key="anywhere" className="chip turn" href={findHref(p, { place: null, country: null })}>Anywhere</Go>] : []),
      ...(uk && p.country !== UK ? [country(UK, "In the UK", uk)] : []),
      ...(abroad && p.country !== ABROAD ? [country(ABROAD, "Abroad", abroad)] : []),
      ...(p.country && p.country !== UK ? away.filter((c) => c.country !== p.country).map((c) => country(c.country, c.country, c.n)) : []),
      ...f.places.map((x) => (
        <Go key={x.place} className="chip" href={findHref(p, { place: x.place })} aria-label={`${x.place}, ${x.n}`}
          aria-current={p.place === x.place ? "true" : undefined}>{x.place}{n(x.n)}</Go>
      )),
    ];
  } else {
    title = `When were the ${what} taken?`;
    const year = yearWord(p);
    const decade = p.yearFrom !== null ? `${Math.floor(p.yearFrom / 10) * 10}s` : null;
    chips = [
      ...(year ? [<Go key="any" className="chip turn" href={findHref(p, { year: null })}>Any time</Go>] : []),
      ...(decade && year !== decade ? [<Go key="decade" className="chip turn" href={findHref(p, { year: decade })}>All the {decade}</Go>] : []),
      ...f.years.map((x) => (
        <Go key={x.label} className="chip" href={findHref(p, { year: x.label })} aria-label={`${x.label}, ${x.n}`}
          aria-current={year === x.label ? "true" : undefined}>{x.label}{n(x.n)}</Go>
      )),
    ];
  }
  return (
    <section className="facet" aria-labelledby="facet-h">
      <h2 id="facet-h" className="facet-h">{title}</h2>
      {chips.length
        ? <Fit key={pick + findHref(p)} label={title} more="More">{[doneChip, ...chips]}</Fit>
        : <><p className="muted">Nothing more to choose here.</p><div className="facet-top">{done}</div></>}
    </section>
  );
}
