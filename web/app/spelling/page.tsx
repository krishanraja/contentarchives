import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Bar from "@/components/Bar";
import Ask from "@/components/Ask";
import { me } from "@/lib/me";
import { isOwner, nextPair, type Side } from "@/lib/respell";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false } };

// Fix a spelling (Krish, 2026-10-21): for the owner only, one pair of names
// at a time that look like one name spelled two ways - "Zora" and "Zara" - and
// three taps: the same person under this spelling, under that one, or two
// people. One pair a screen, so it never scrolls; the next comes after a tap.
export default async function Spelling({ searchParams }: { searchParams: Promise<{ kept?: string; was?: string; n?: string }> }) {
  const who = await me();
  if (!(await isOwner(who))) notFound();
  const sp = await searchParams;
  const { pair, left } = await nextPair(who!);
  const face = (s: Side) => (
    <div className="spell-side">
      {s.cover ? <img src={`/face/${encodeURIComponent(s.cover)}`} alt="" /> : <span className="spell-noface" aria-hidden="true" />}
      <b>{s.name}</b>
      <span className="muted">{s.n.toLocaleString("en-GB")} {s.n === 1 ? "photo" : "photos"}</span>
    </div>
  );
  const keep = (s: Side, other: Side) => (
    <Ask action="/api/spelling" op="same" hidden={{ a: pair!.a.name, b: pair!.b.name, keep: s.name }}
      label={`Same person: call them ${s.name}`} busy="Saving…" tint="mint" key={s.name}>
      {other.others > 0 && <p className="muted spell-note">{other.others === 1 ? "1 answer" : `${other.others} answers`} from
        someone else still {other.others === 1 ? "says" : "say"} {other.name}: only they can change {other.others === 1 ? "it" : "them"}.</p>}
    </Ask>
  );
  return (
    <>
      <Bar title="Fix a spelling" />
      <main className="page middle spell">
        {sp.kept && sp.was && <p role="status" className="notice">{sp.was} is now {sp.kept}{sp.n ? `, on ${Number(sp.n).toLocaleString("en-GB")} photos` : ""}.</p>}
        {!pair
          ? <div className="card"><h2>Nothing left to check</h2><p className="muted">No two names look like one name spelled two ways.</p></div>
          : <div className="card stack">
              <h2>Are these the same person?</h2>
              <div className="spell-pair">{face(pair.a)}{face(pair.b)}</div>
              {keep(pair.a, pair.b)}
              {keep(pair.b, pair.a)}
              <Ask action="/api/spelling" op="different" hidden={{ a: pair.a.name, b: pair.b.name }}
                label="No, two different people" busy="Saving…" tint="quiet" />
              {left > 0 && <p className="muted">{left} more {left === 1 ? "pair" : "pairs"} to look at after this.</p>}
            </div>}
      </main>
    </>
  );
}
