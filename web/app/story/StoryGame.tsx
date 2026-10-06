"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Undo from "@/components/Undo";
import Confetti from "@/components/Confetti";
import Shot from "@/components/Shot";
import Fit from "@/components/Fit";
import YearPicker from "@/components/YearPicker";
import { send, uuid } from "@/components/outbox";
import { close, exact } from "@/lib/spelling";

type S = { hash: string; needPlace: boolean; needYear: boolean; day: string[]; places: string[] } | null;
type Step = "place" | "spell" | "day" | "decade" | "thanks";

const img = (h: string, size = "v") => `/img/${size}/${encodeURIComponent(h)}`;

export default function StoryGame({ only }: { only: string | null }) {
  const [s, setS] = useState<S | undefined>(undefined);
  const [step, setStep] = useState<Step>("place");
  const [place, setPlace] = useState("");
  const [typing, setTyping] = useState(false);
  const [labelled, setLabelled] = useState(0);
  const [last, setLast] = useState<{ id: string; text: string } | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [single, setSingle] = useState(only);
  const [known, setKnown] = useState<string[]>([]);
  const [meant, setMeant] = useState<string[]>([]);

  const load = useCallback(async (after: string[], one: string | null) => {
    setS(undefined); setErr(""); setPlace(""); setTyping(false); setLabelled(0);
    const r = await fetch(`/api/story/next?after=${after.join(",")}${one ? `&photo=${encodeURIComponent(one)}` : ""}`)
      .then((x) => x.json()).catch(() => undefined);
    if (r === undefined) { setErr("No internet connection. Your answers are safe on this phone."); setS(null); return; }
    setS(r);
    if (r) setStep(r.needPlace ? "place" : r.needYear ? "decade" : "thanks");
  }, []);
  useEffect(() => { void load([], only); }, [load, only]);
  useEffect(() => { fetch("/api/names").then((r) => r.json()).then((j) => setKnown(j.places || [])).catch(() => undefined); }, []);

  // a typed place spelled the way the family already spells it is that place;
  // a near miss ("Naintal") is asked about, never changed without a tap
  function typedPlace() {
    const v = place.trim().replace(/\s+/g, " ");
    if (v.length < 2) return;
    const all = [...new Set([...(s?.places || []), ...known])];
    const same = exact(v, all);
    if (same) { pickPlace(same); return; }
    const near = close(v, all);
    if (near.length) { setMeant(near); setStep("spell"); return; }
    pickPlace(v);
  }

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

  // "I don't know" sends this photo to the back of THIS person's queue (it comes
  // back once they have seen the rest); everyone else is still asked it
  async function shrug() {
    if (!s) return;
    await fetch("/api/skip", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: "story:" + s.hash }) }).catch(() => undefined);
  }
  async function skip() {
    await shrug();
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
      <div className="game middle">
        {err ? <p className="notice error">{err}</p> : <div className="yay"><h2>All done!</h2><p>Every photo has a place and a year. Amazing.</p></div>}
        <Link className="btn block sun" href="/">Back home</Link>
      </div>
    );
  }

  // One screen per step, never scrolling (Krish, 2026-10-05): the photo takes
  // the room the step leaves it; a list of places longer than its room turns.
  const typedNow = place.trim().replace(/\s+/g, " ");
  return (
    <div className={step === "decade" ? "game picking" : "game"}>
      {step === "thanks" && labelled > 0 && <Confetti seed={labelled} />}
      <Shot src={img(s.hash)} alt="A family photo" />
      <div className="panel">
        {err && <p className="notice error" role="alert">{err}</p>}

        {step === "place" && (
          <>
            <h2>Where was this taken?</h2>
            {!typing ? (
              <>
                {s.places.length > 0 && (
                  <Fit label="Places" more="More places">
                    {s.places.map((p) => <button key={p} className="chip" onClick={() => pickPlace(p)}>{p}</button>)}
                  </Fit>
                )}
                <div className="row">
                  <button className="btn sky" onClick={() => setTyping(true)}>{s.places.length ? "Somewhere else" : "Type the place"}</button>
                  <button className="btn" onClick={s.needYear ? () => { void shrug(); setStep("decade"); } : skip}>I don't know</button>
                </div>
              </>
            ) : (
              <form className="contents" onSubmit={(e) => { e.preventDefault(); typedPlace(); }}>
                <label className="sr" htmlFor="pl">The place</label>
                <input id="pl" className="field" value={place} onChange={(e) => setPlace(e.target.value)} placeholder="A town, a house, a country…" autoCapitalize="words" enterKeyHint="done" />
                <div className="row">
                  <button type="button" className="btn" onClick={s.needYear ? () => { void shrug(); setStep("decade"); } : skip}>I don't know</button>
                  <button className="btn mint">Save this place</button>
                </div>
              </form>
            )}
          </>
        )}

        {step === "spell" && (
          <>
            <h2>Did you mean {meant.length === 1 ? `${meant[0]}?` : "one of these?"}</h2>
            <Fit label="Places we already know" more="More places">
              {meant.map((p) => <button key={p} className="chip" onClick={() => pickPlace(p)}>{p}</button>)}
            </Fit>
            <div className="row">
              <button className="btn" onClick={() => setStep("place")}>Change what I typed</button>
              <button className="btn" onClick={() => pickPlace(typedNow)}>No, save “{typedNow}”</button>
            </div>
          </>
        )}

        {step === "day" && (
          <>
            <h2>Also label the {s.day.length} other {s.day.length === 1 ? "photo" : "photos"} from that day?</h2>
            <div className="strip">{s.day.slice(0, 4).map((h) => <img key={h} src={img(h, "t")} alt="" />)}</div>
            <div className="row">
              <button className="btn" onClick={() => savePlace([s.hash])}>Just this one</button>
              <button className="btn mint" onClick={() => savePlace([s.hash, ...s.day])}>Yes, all of them</button>
            </div>
          </>
        )}

        {step === "decade" && (
          <YearPicker cancel="I don't know" onCancel={() => { void shrug(); setStep("thanks"); }} onPick={saveYear} />
        )}

        {step === "thanks" && (
          <>
            <div className="yay">
              {labelled > 0 ? <h2>{labelled.toLocaleString("en-GB")} {labelled === 1 ? "photo" : "photos"} labelled. Thank you!</h2> : <h2>No problem!</h2>}
            </div>
            <div className="row">
              <Link className="btn" href="/">I'm done</Link>
              <button className="btn mint" onClick={next}>{single ? "Do another" : "Next photo"}</button>
            </div>
          </>
        )}
        {last && <Undo text={last.text} onUndo={undo} onDone={() => setLast(null)} />}
      </div>
    </div>
  );
}
