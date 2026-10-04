"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Undo from "@/components/Undo";
import Confetti from "@/components/Confetti";
import { send, uuid } from "@/components/outbox";

type S = { hash: string; needPlace: boolean; needYear: boolean; day: string[]; places: string[] } | null;
type Step = "place" | "day" | "decade" | "year" | "thanks";

const img = (h: string, size = "v") => `/img/${size}/${encodeURIComponent(h)}`;
const DECADES = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020];

export default function StoryGame({ only }: { only: string | null }) {
  const [s, setS] = useState<S | undefined>(undefined);
  const [step, setStep] = useState<Step>("place");
  const [place, setPlace] = useState("");
  const [typing, setTyping] = useState(false);
  const [decade, setDecade] = useState<number | null>(null);
  const [labelled, setLabelled] = useState(0);
  const [last, setLast] = useState<{ id: string; text: string } | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [single, setSingle] = useState(only);

  const load = useCallback(async (after: string[], one: string | null) => {
    setS(undefined); setErr(""); setPlace(""); setTyping(false); setDecade(null); setLabelled(0);
    const r = await fetch(`/api/story/next?after=${after.join(",")}${one ? `&photo=${encodeURIComponent(one)}` : ""}`)
      .then((x) => x.json()).catch(() => undefined);
    if (r === undefined) { setErr("No internet connection. Your answers are safe on this phone."); setS(null); return; }
    setS(r);
    if (r) setStep(r.needPlace ? "place" : r.needYear ? "decade" : "thanks");
  }, []);
  useEffect(() => { void load([], only); }, [load, only]);

  function after() {
    if (!s) return;
    if (step === "place" || step === "day") setStep(s.needYear ? "decade" : "thanks");
    else setStep("thanks");
  }

  async function savePlace(hashes: string[]) {
    const id = uuid();
    const r = await send({ id, kind: "place", hashes, value: place });
    if (!r.ok && r.error && !r.error.startsWith("offline")) { setErr(r.error); return; }
    setLabelled((n) => n + (r.labelled ?? hashes.length));
    setLast({ id, text: `Saved: ${place}` });
    after();
  }

  function pickPlace(p: string) {
    setPlace(p);
    if (s && s.day.length) setStep("day");
    else void (async () => {
      const id = uuid();
      const r = await send({ id, kind: "place", hashes: [s!.hash], value: p });
      if (!r.ok && r.error && !r.error.startsWith("offline")) { setErr(r.error); return; }
      setLabelled((n) => n + 1); setLast({ id, text: `Saved: ${p}` }); after();
    })();
  }

  async function saveYear(v: string) {
    if (!s) return;
    const id = uuid();
    const r = await send({ id, kind: "year", hashes: [s.hash], value: v });
    if (!r.ok && r.error && !r.error.startsWith("offline")) { setErr(r.error); return; }
    setLabelled((n) => Math.max(n, 1)); setLast({ id, text: `Saved: ${v}` }); setStep("thanks");
  }

  async function skip() {
    if (!s) return;
    await fetch("/api/skip", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: "story:" + s.hash }) }).catch(() => undefined);
    next();
  }
  function next() {
    const n = s ? [...seen, s.hash] : seen;
    setSeen(n); setSingle(null); void load(n, null);
  }
  async function undo() {
    if (!last) return;
    await fetch("/api/answers/undo", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: last.id }) }).catch(() => undefined);
    setLast(null); void load(seen, s?.hash || null);
  }

  if (s === undefined) return <p className="sentence" role="status">Finding a photo…</p>;
  if (s === null) {
    return (
      <div className="stack">
        {err ? <p className="notice error">{err}</p> : <div className="yay"><h2>All done!</h2><p>Every photo has a place and a year. Amazing.</p></div>}
        <Link className="btn block sun" href="/">Back home</Link>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 18 }}>
      {step === "thanks" && labelled > 0 && <Confetti seed={labelled} />}
      <div className="hero"><img src={img(s.hash)} alt="A family photo" /></div>
      {err && <p className="notice error" role="alert">{err}</p>}

      {step === "place" && (
        <div className="card">
          <h2>Where was this taken?</h2>
          {!typing && s.places.length > 0 && (
            <div className="chips">{s.places.map((p) => <button key={p} className="chip" onClick={() => pickPlace(p)}>{p}</button>)}</div>
          )}
          {!typing ? (
            <button className="btn block sky" onClick={() => setTyping(true)}>{s.places.length ? "Somewhere else" : "Type the place"}</button>
          ) : (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); if (place.trim().length > 1) pickPlace(place.trim()); }}>
              <label className="sr" htmlFor="pl">The place</label>
              <input id="pl" className="field" value={place} onChange={(e) => setPlace(e.target.value)} placeholder="A town, a house, a country…" autoCapitalize="words" enterKeyHint="done" />
              <button className="btn block mint">Save this place</button>
            </form>
          )}
          <button className="btn block" onClick={s.needYear ? () => setStep("decade") : skip}>I don't know</button>
        </div>
      )}

      {step === "day" && (
        <div className="card">
          <h2>Also label the {s.day.length} other {s.day.length === 1 ? "photo" : "photos"} from that day?</h2>
          <div className="samples">{s.day.slice(0, 8).map((h) => <img key={h} src={img(h, "t")} alt="" style={{ borderRadius: 14 }} />)}</div>
          <button className="btn block mint" onClick={() => savePlace([s.hash, ...s.day])}>Yes, all of them</button>
          <button className="btn block" onClick={() => savePlace([s.hash])}>Just this one</button>
        </div>
      )}

      {step === "decade" && (
        <div className="card">
          <h2>Roughly what year?</h2>
          <p className="muted">A guess is fine.</p>
          <div className="chips">{DECADES.map((d) => <button key={d} className="chip" onClick={() => { setDecade(d); setStep("year"); }}>{d}s</button>)}</div>
          <button className="btn block" onClick={() => setStep("thanks")}>I don't know</button>
        </div>
      )}

      {step === "year" && decade && (
        <div className="card">
          <h2>Which year in the {decade}s?</h2>
          <div className="chips">{Array.from({ length: 10 }, (_, i) => decade + i).filter((y) => y <= new Date().getFullYear()).map((y) => <button key={y} className="chip" onClick={() => saveYear(String(y))}>{y}</button>)}</div>
          <button className="btn block mint" onClick={() => saveYear(`${decade}s`)}>Just “the {decade}s”</button>
        </div>
      )}

      {step === "thanks" && (
        <div className="stack">
          <div className="yay">
            {labelled > 0 ? (<><p className="big">{labelled}</p><h2>{labelled === 1 ? "photo" : "photos"} labelled. Thank you!</h2></>) : <h2>No problem!</h2>}
          </div>
          <button className="btn block mint" onClick={next}>{single ? "Do another photo" : "Next photo"}</button>
          <Link className="btn block" href="/">I'm done for now</Link>
        </div>
      )}
      {last && <Undo text={last.text} onUndo={undo} onDone={() => setLast(null)} />}
    </div>
  );
}
