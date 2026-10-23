import Link from "next/link";
import { counts, nextFace, nextStory } from "@/lib/data";
import { me } from "@/lib/me";
import { Face, Pin, Search } from "@/components/icons";

export const dynamic = "force-dynamic";

function cap(s: string) { return s.replace(/(^|\s)\p{L}/gu, (m) => m.toUpperCase()); }
const n = (x: number) => x.toLocaleString("en-GB");

// Home (Krish, 2026-10-23: "the next best action isn't always right there"):
// hello, a search box, then the ONE next thing this person can help with, shown
// with its own picture and one button. The other ways in sit quietly under it.
// A face to name comes before a photo to place: a name is what the family
// knows best, and it labels every photo of that person at once.
export default async function Home() {
  const [who, c] = await Promise.all([me(), counts()]);
  const face = who && c.faces > 0 ? await nextFace(who).catch(() => null) : null;
  const story = who && !face && c.story > 0 ? await nextStory(who).catch(() => null) : null;
  const next = face
    ? { href: "/help", src: `/face/${encodeURIComponent(face.hero.key)}?whole=1`, ask: "Who is this?", go: "Tell us who" }
    : story
      ? { href: "/story", src: `/img/v/${encodeURIComponent(story.hash)}`, ask: story.needPlace ? "Where was this taken?" : "Roughly what year?", go: "Tell us" }
      : null;
  return (
    <main className="page home">
      <div className="hello">
        <h1>Hello{who ? `, ${cap(who)}` : ""}!</h1>
        {/* photos AND videos (Krish, 2026-10-11): the opening screens had only ever said photos */}
        <p className="muted">{n(c.photos)} family photos{c.videos ? <> and {n(c.videos)} videos</> : null}</p>
      </div>
      {/* a real GET form: it works before the page's script arrives */}
      <form role="search" method="get" action="/find" className="pillsearch">
        <label className="sr" htmlFor="q">Find a person, place or year</label>
        <input id="q" name="q" type="search" placeholder="Find a person, place or year" enterKeyHint="search" autoComplete="off" />
        <button className="btn sky" aria-label="Search"><Search /></button>
      </form>
      {next && (
        <Link href={next.href} className="nextup">
          <span className="kicker">You can help with this</span>
          <span className="slot"><span className="frame"><img src={next.src} alt="" /></span></span>
          <h2>{next.ask}</h2>
          <span className="btn block tomato">{next.go}</span>
        </Link>
      )}
      <nav className="tasks" aria-label="More to do">
        {!next && <Link href="/find" className="task">
          <span className="ic" style={{ background: "var(--sun)" }}><Search /></span>
          <span><b>Find photos &amp; videos</b><small>A person, a place or a year</small></span>
          <span className="n" aria-hidden="true">›</span>
        </Link>}
        <Link href="/help" className="task">
          <span className="ic" style={{ background: "var(--pink)" }}><Face /></span>
          <span><b>Who is this?</b><small>Put names to faces</small></span>
          <span className="n">{c.faces > 0 ? `${n(c.faces)} to name ›` : "All done ›"}</span>
        </Link>
        <Link href="/story" className="task">
          <span className="ic" style={{ background: "var(--mint)" }}><Pin /></span>
          <span><b>Where and when?</b><small>Place a photo, or its year</small></span>
          <span className="n">{c.story > 0 ? `${n(c.story)} to place ›` : "All done ›"}</span>
        </Link>
      </nav>
      {/* a phone or tablet passed around the family: the next person says who they are */}
      {who && <Link href="/who?change" className="btn quiet notme">Not {cap(who)}?</Link>}
    </main>
  );
}
