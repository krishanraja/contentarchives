import Link from "next/link";
import Bar from "@/components/Bar";
import { browse, facets, search } from "@/lib/data";
import { describe } from "@/lib/search";
import { asMedia, findHref, PICKS, type Media, type Pick } from "@/lib/search";
import SearchBox from "./SearchBox";
import Results from "./Results";
import TypeSwitch from "./TypeSwitch";
import FilterBar from "./FilterBar";
import FacetPanel from "./FacetPanel";
import Fit from "@/components/Fit";

export const dynamic = "force-dynamic";

// the decade this library has the most photographs from, as a search to try
function exampleYears(decades: { decade: number; n: number }[]) {
  const top = [...decades].sort((a, b) => b.n - a.n)[0];
  return top ? `${top.decade}s` : "";
}

// a browse link: the words, with the type in force carried along
const go = (q: string, type: Media | null) => {
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (type) qs.set("type", type);
  const s = qs.toString();
  return s ? `/find?${s}` : "/find";
};

type SP = { q?: string; show?: string; type?: string; pick?: string; say?: string };

export default async function Find({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  // "say" is what the Say panel's form sends: more words for the same search
  const q = [sp.q || "", sp.say || ""].join(" ").replace(/\s+/g, " ").trim();
  const type = asMedia(sp.type);
  const pick = PICKS.includes(sp.pick as Pick) ? (sp.pick as Pick) : null;
  if (q || pick) {
    const r = await search(q, 0, type);
    const p = r.parsed;
    const f = await facets(p);
    const listKey = findHref(p);
    return (
      <>
        <Bar title="Photos & videos" />
        <main className="page find results">
          <SearchBox initial={q} type={p.media} />
          <TypeSwitch active={p.media} counts={f.media} href={(m) => findHref(p, { media: m }, pick)} />
          <FilterBar p={p} open={pick} />
          {pick
            ? <FacetPanel key={pick} p={p} pick={pick} f={f} />
            : <>
                <p className="sentence" role="status">{r.total ? describe(p, r.total, r.mode, f.media)
                  : q ? `Nothing found for “${q}”. Take something off above, or try a name, a place or a year.`
                  : "Nothing found."}</p>
                {/* keyed by the whole search: a new search is a new grid, never the last one's photos under a new sentence */}
                {r.total > 0 && <Results key={listKey} q={r.q} type={p.media} first={r.cards} total={r.total} />}
              </>}
        </main>
      </>
    );
  }
  // One list at a time, chosen with three buttons (real links, so they
  // work before the script arrives); the list turns like pages, never scrolls.
  const b = await browse(type);
  const lists = [
    { key: "people", name: "People", n: b.people.length },
    { key: "places", name: "Places", n: b.places.length },
    { key: "years", name: "Years", n: b.decades.length },
  ].filter((l) => l.n > 0);
  const show = lists.find((l) => l.key === sp.show)?.key || lists[0]?.key;
  const tab = (key: string, m: Media | null) => {
    const qs = new URLSearchParams();
    if (key !== lists[0]?.key) qs.set("show", key);
    if (m) qs.set("type", m);
    const s = qs.toString();
    return s ? `/find?${s}` : "/find";
  };
  return (
    <>
      <Bar title="Photos & videos" />
      <main className="page find">
        <SearchBox initial="" type={type} example={exampleYears(b.decades)} />
        <TypeSwitch active={type} counts={b.media} href={(m) => tab(show || "", m)} />
        {lists.length > 1 && (
          <nav className="tabs" aria-label="Look through">
            {lists.map((l) => (
              <Link key={l.key} className="btn small" href={tab(l.key, type)}
                aria-current={l.key === show ? "page" : undefined}>{l.name}</Link>
            ))}
          </nav>
        )}
        {show === "people" && (
          <Fit key={"people" + type} label="People" more="More people">
            {b.people.map((x) => (
              <Link key={x.name} className="chip" href={go(x.name, type)}>
                {x.cover && <img src={`/face/${encodeURIComponent(x.cover)}`} alt="" />}
                {x.name}
              </Link>
            ))}
          </Fit>
        )}
        {show === "places" && (
          <Fit key={"places" + type} label="Places" more="More places">
            {b.places.map((x) => (
              <Link key={x.place} className="chip" href={go(x.place, type)}>{x.place}</Link>
            ))}
          </Fit>
        )}
        {show === "years" && (
          <Fit key={"years" + type} label="Years">
            {b.decades.map((d) => (
              <Link key={d.decade} className="chip" href={go(`${d.decade}s`, type)}>{d.decade}s</Link>
            ))}
          </Fit>
        )}
      </main>
    </>
  );
}
