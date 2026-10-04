import Link from "next/link";
import Bar from "@/components/Bar";
import { browse, search } from "@/lib/data";
import SearchBox from "./SearchBox";
import Results from "./Results";

export const dynamic = "force-dynamic";

export default async function Find({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const q = ((await searchParams).q || "").trim();
  if (q) {
    const r = await search(q);
    return (
      <>
        <Bar title="Find photos" />
        <main className="page">
          <SearchBox initial={q} />
          <p className="sentence" role="status">{r.total ? r.sentence : `Nothing found for “${q}”. Try a name, a place or a year.`}</p>
          <Results q={q} first={r.cards} total={r.total} />
        </main>
      </>
    );
  }
  const b = await browse();
  return (
    <>
      <Bar title="Find photos" />
      <main className="page">
        <SearchBox initial="" />
        {b.people.length > 0 && (
          <section className="stack">
            <h2>People</h2>
            <div className="chips">
              {b.people.slice(0, 24).map((p) => (
                <Link key={p.name} className="chip" href={`/find?q=${encodeURIComponent(p.name)}`}>
                  {p.cover && <img src={`/face/${encodeURIComponent(p.cover)}`} alt="" />}
                  {p.name}
                </Link>
              ))}
            </div>
          </section>
        )}
        {b.places.length > 0 && (
          <section className="stack">
            <h2>Places</h2>
            <div className="chips">
              {b.places.slice(0, 20).map((p) => (
                <Link key={p.place} className="chip" href={`/find?q=${encodeURIComponent(p.place)}`}>{p.place}</Link>
              ))}
            </div>
          </section>
        )}
        {b.decades.length > 0 && (
          <section className="stack">
            <h2>Years</h2>
            <div className="chips">
              {b.decades.map((d) => (
                <Link key={d.decade} className="chip" href={`/find?q=${d.decade}s`}>{d.decade}s</Link>
              ))}
            </div>
          </section>
        )}
      </main>
    </>
  );
}
