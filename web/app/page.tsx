import Link from "next/link";
import { counts } from "@/lib/data";
import { me } from "@/lib/me";
import { Face, Pin, Search } from "@/components/icons";
import Squeeze from "@/components/Squeeze";

export const dynamic = "force-dynamic";

function cap(s: string) { return s.replace(/(^|\s)\p{L}/gu, (m) => m.toUpperCase()); }

export default async function Home() {
  const [who, c] = await Promise.all([me(), counts()]);
  return (
    <main className="page">
      <div style={{ flex: "none" }}>
        <h1>Hello{who ? `, ${cap(who)}` : ""}!</h1>
        <p className="muted" style={{ marginTop: 6 }}>{c.photos.toLocaleString("en-GB")} family photos are here.</p>
      </div>
      <Squeeze className="tiles" levels={3}>
      <Link href="/find" className="tile" style={{ background: "var(--sun)" }}>
        <span className="icon"><Search /></span>
        <span><h2>Find photos</h2><p>Look for a person, a place or a year.</p></span>
      </Link>
      <Link href="/help" className="tile" style={{ background: "var(--pink)" }}>
        <span className="icon"><Face /></span>
        <span><h2>Who is this?</h2><p>Help us put names to faces.</p>
          {c.faces > 0 && <span className="count">{c.faces.toLocaleString("en-GB")} faces to name</span>}</span>
      </Link>
      <Link href="/story" className="tile" style={{ background: "var(--mint)" }}>
        <span className="icon"><Pin /></span>
        <span><h2>Where and when?</h2><p>Tell us where a photo was taken, or roughly what year.</p>
          {c.story > 0 && <span className="count">{c.story.toLocaleString("en-GB")} photos to place</span>}</span>
      </Link>
      </Squeeze>
      {/* a phone or tablet passed around the family: the next person says who they are */}
      {who && <Link href="/who" className="btn block quiet" style={{ flex: "none" }}>Not {cap(who)}? Tap here</Link>}
    </main>
  );
}
