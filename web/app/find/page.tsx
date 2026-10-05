import Link from "next/link";
import Bar from "@/components/Bar";
import { browse, search } from "@/lib/data";
import SearchBox from "./SearchBox";
import Results from "./Results";
import Fit from "@/components/Fit";

export const dynamic = "force-dynamic";

// the decade this library has the most photographs from, as a search to try
function exampleYears(decades: { decade: number; n: number }[]) {
  const top = [...decades].sort((a, b) => b.n - a.n)[0];
  return top ? `${top.decade}s` : "";
}

export default async function Find({ searchParams }: { searchParams: Promise<{ q?: string; show?: string }> }) {
  const sp = await searchParams;
  const q = (sp.q || "").trim();
  if (q) {
    const r = await search(q);
    return (
      <>
        <Bar title="Find photos" />
        <main className="page find">
          <SearchBox initial={q} />
          <p className="sentence" role="status">{r.total ? r.sentence : `Nothing found for “${q}”. Try a name, a place or a year.`}</p>
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
