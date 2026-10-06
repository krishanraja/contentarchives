import Link from "next/link";
import Bar from "@/components/Bar";
import { browse, compose, refine, search, type Refine } from "@/lib/data";
import type { Parsed } from "@/lib/search";
import SearchBox from "./SearchBox";
import Results from "./Results";
import Fit from "@/components/Fit";

export const dynamic = "force-dynamic";

// the decade this library has the most photographs from, as a search to try
function exampleYears(decades: { decade: number; n: number }[]) {
  const top = [...decades].sort((a, b) => b.n - a.n)[0];
  return top ? `${top.decade}s` : "";
}

// One row of chips under a search: the years of the person (or place) chosen,
// or the people in the year chosen. A chip is a link, so it works before the
// page's script arrives; the row turns its pages with "More ›".
function RefineRow({ rf, p }: { rf: Refine; p: Parsed }) {
  const go = (q: string) => `/find?q=${encodeURIComponent(q)}`;
  if (rf.kind === "years") {
    return (
      <Fit one label="Years" more="More years">
        {[
          ...(rf.active ? [<Link key="all" className="chip turn" href={go(compose(p, { year: null }))}>All years</Link>] : []),
          ...rf.items.map((y) => (
            <Link key={y.label} className="chip" href={go(compose(p, { year: y.label }))}
              aria-current={rf.active === y.label ? "true" : undefined}>{y.label}</Link>
          )),
        ]}
      </Fit>
    );
  }
  return (
    <Fit one label="Who is in these photos" more="More people">
      {rf.items.map((x) => (
        <Link key={x.name} className="chip" href={go(compose(p, { people: [x.name] }))}>
          {x.cover && <img src={`/face/${encodeURIComponent(x.cover)}`} alt="" />}{x.name}
        </Link>
      ))}
    </Fit>
  );
}

export default async function Find({ searchParams }: { searchParams: Promise<{ q?: string; show?: string }> }) {
  const sp = await searchParams;
  const q = (sp.q || "").trim();
  if (q) {
    const r = await search(q);
    const rf = r.total ? await refine(r.parsed) : null;
    return (
      <>
        <Bar title="Find photos" />
        <main className="page find">
          <SearchBox initial={q} />
          <p className="sentence" role="status">{r.total ? r.sentence : `Nothing found for “${q}”. Try a name, a place or a year.`}</p>
          {rf && <RefineRow key={"refine:" + q} rf={rf} p={r.parsed} />}
          {/* keyed by the words: a new search is a new grid, never the last one's photos under a new sentence */}
          {r.total > 0 && <Results key={q} q={q} first={r.cards} total={r.total} />}
        </main>
      </>
    );
  }
  // One list at a time, chosen with three big buttons (real links, so they
  // work before the script arrives); the list turns like pages, never scrolls.
  const b = await browse();
  const lists = [
    { key: "people", name: "People", n: b.people.length },
    { key: "places", name: "Places", n: b.places.length },
    { key: "years", name: "Years", n: b.decades.length },
  ].filter((l) => l.n > 0);
  const show = lists.find((l) => l.key === sp.show)?.key || lists[0]?.key;
  return (
    <>
      <Bar title="Find photos" />
      <main className="page find">
        <SearchBox initial="" example={exampleYears(b.decades)} />
        {lists.length > 1 && (
          <nav className="tabs" aria-label="Look through">
            {lists.map((l) => (
              <Link key={l.key} className="btn small" href={l.key === lists[0].key ? "/find" : `/find?show=${l.key}`}
                aria-current={l.key === show ? "page" : undefined}>{l.name}</Link>
            ))}
          </nav>
        )}
        {show === "people" && (
          <Fit key="people" label="People" more="More people">
            {b.people.map((p) => (
              <Link key={p.name} className="chip" href={`/find?q=${encodeURIComponent(p.name)}`}>
                {p.cover && <img src={`/face/${encodeURIComponent(p.cover)}`} alt="" />}
                {p.name}
              </Link>
            ))}
          </Fit>
        )}
        {show === "places" && (
          <Fit key="places" label="Places" more="More places">
            {b.places.map((p) => (
              <Link key={p.place} className="chip" href={`/find?q=${encodeURIComponent(p.place)}`}>{p.place}</Link>
            ))}
          </Fit>
        )}
        {show === "years" && (
          <Fit key="years" label="Years">
            {b.decades.map((d) => (
              <Link key={d.decade} className="chip" href={`/find?q=${d.decade}s`}>{d.decade}s</Link>
            ))}
          </Fit>
        )}
      </main>
    </>
  );
}
