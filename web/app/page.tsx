import Link from "next/link";
import { browse, counts, nextFace } from "@/lib/data";
import { me } from "@/lib/me";
import { Face, Pin, Search } from "@/components/icons";
import Fit from "@/components/Fit";

export const dynamic = "force-dynamic";

function cap(s: string) { return s.replace(/(^|\s)\p{L}/gu, (m) => m.toUpperCase()); }
const n = (x: number) => x.toLocaleString("en-GB");

// Home (Krish, 2026-10-23: "I prefer the home screen having all of our faces
// to choose from to start the exploration... a slightly more subtle way of
// getting people to add information"): hello, a search box, then the family's
// faces - tap one to see their photos. Asking for help is quieter: one face
// nobody has named sits among them with a "?", and the two ways to help sit
// under the faces as rows, with what is left.
export default async function Home() {
  const [who, c, b] = await Promise.all([me(), counts(), browse(null)]);
  // a different face on every visit; tapping it asks about that same face first
  const face = who && c.faces > 0 ? await nextFace(who, [], { shuffle: true }).catch(() => null) : null;
  const people = b.people.filter((p) => p.cover);
  const faces = people.map((p) => (
    <Link key={p.name} className="face" href={`/find?q=${encodeURIComponent(p.name)}`}>
      <img src={`/face/${encodeURIComponent(p.cover!)}`} alt="" />
      <span>{p.name.split(" ")[0]}</span>
      <span className="sr"> {p.name}, {n(p.n)} photos</span>
    </Link>
  ));
  // third in the list, so it is on the first page whatever the screen holds
  if (face) faces.splice(Math.min(2, faces.length), 0, (
    <Link key="?" className="face unknown" href={`/help?g=${encodeURIComponent(face.group)}`} aria-label="Someone nobody has named yet. Who is this?">
      <img src={`/face/${encodeURIComponent(face.hero.key)}`} alt="" />
      <span>Who?</span>
    </Link>
  ));
  return (
    <main className="page home">
      <div className="hello">
        <div>
          <h1>Hello{who ? `, ${cap(who)}` : ""}!</h1>
          {/* photos AND videos (Krish, 2026-10-11): the opening screens had only ever said photos */}
          <p className="muted">{n(c.photos)} family photos{c.videos ? <> and {n(c.videos)} videos</> : null}</p>
        </div>
        {/* top right (Krish, 2026-10-24); a plain form, so it works before the script arrives */}
        <form method="post" action="/api/signout" className="signout">
          <button className="btn quiet small">Sign out</button>
        </form>
      </div>
      {/* a real GET form: it works before the page's script arrives */}
      <form role="search" method="get" action="/find" className="pillsearch">
        <label className="sr" htmlFor="q">Find a person, place or year</label>
        <input id="q" name="q" type="search" placeholder="Find a person, place or year" enterKeyHint="search" autoComplete="off" />
        <button className="btn sky" aria-label="Search"><Search /></button>
      </form>
      {faces.length > 0
        ? <Fit className="faces" label="People" more="More people">{faces}</Fit>
        : <Link href="/find" className="btn block sun">Look through the photos</Link>}
      {/* the ways to help keep their icon rows (Krish, 2026-10-23), under the faces */}
      <nav className="tasks" aria-label="Help the family">
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
