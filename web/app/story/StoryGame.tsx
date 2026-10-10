"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Undo from "@/components/Undo";
import Confetti from "@/components/Confetti";
import Shot from "@/components/Shot";
import YearPicker from "@/components/YearPicker";
import PlacePicker from "@/components/PlacePicker";
import { send, uuid } from "@/components/outbox";
import { ahead } from "@/components/ahead";

type S = { hash: string; needPlace: boolean; needYear: boolean; day: string[]; places: string[] } | null;
type Step = "place" | "day" | "decade" | "thanks";

const img = (h: string, size = "v") => `/img/${size}/${encodeURIComponent(h)}`;
const getStory = (after: string[], one: string | null): Promise<S | undefined> =>
  fetch(`/api/story/next?after=${after.join(",")}${one ? `&photo=${encodeURIComponent(one)}` : ""}`)
    .then((x) => x.json()).catch(() => undefined);
const pictures = (s: NonNullable<S>) => [img(s.hash), ...s.day.slice(0, 4).map((h) => img(h, "t"))];

export default function StoryGame({ only }: { only: string | null }) {
  const [s, setS] = useState<S | undefined>(undefined);
  const [step, setStep] = useState<Step>("place");
  const [place, setPlace] = useState("");
  const [labelled, setLabelled] = useState(0);
  const [last, setLast] = useState<{ id: string; text: string } | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [single, setSingle] = useState(only);
  const upcoming = useRef(ahead<S>());
  // an answer still on its way: undo waits for it, or it would arrive after the undo
  const sending = useRef(new Map<string, Promise<unknown>>());

  const load = useCallback(async (after: string[], one: string | null) => {
    const held = upcoming.current.take(`${after.join(",")}|${one || ""}`);
    if (!held?.ready) setS(undefined);
    setErr(""); setPlace(""); setLabelled(0);
    let r = held ? await held.p : undefined;
    if (r === undefined) r = await getStory(after, one);
    if (r === undefined) { setErr("No internet connection. Your answers are safe on this phone."); setS(null); return; }
    setS(r);
    if (r) {
      setStep(r.needPlace ? "place" : r.needYear ? "decade" : "thanks");
      const then = [...after, r.hash];
      upcoming.current.start(`${then.join(",")}|`, () => getStory(then, null), pictures);
    }
  }, []);

  // The step moves on at the tap; the outbox keeps the answer until the
  // server has it, and a refusal is shown in the panel as before.
  function keep(body: Record<string, unknown> & { id: string }) {
    const p = send(body);
    sending.current.set(body.id, p);
    void p.then((r) => {
      sending.current.delete(body.id);
      if (!r.ok && r.error && !r.error.startsWith("offline")) setErr(r.error);
    });
  }
  useEffect(() => { void load([], only); }, [load, only]);

  function after() {
    if (!s) return;
    if (step === "place" || step === "day") setStep(s.needYear ? "decade" : "thanks");
    else setStep("thanks");
  }

  function savePlace(hashes: string[]) {
    const id = uuid();
    keep({ id, kind: "place", hashes, value: place });
    setLabelled((n) => n + hashes.length);
    setLast({ id, text: `Saved: ${place}` });
    after();
  }

  function pickPlace(p: string) {
    setPlace(p);
    if (s && s.day.length) setStep("day");
    else {
      const id = uuid();
      keep({ id, kind: "place", hashes: [s!.hash], value: p });
      setLabelled((n) => n + 1); setLast({ id, text: `Saved: ${p}` }); after();
    }
  }

  function saveYear(v: string) {
    if (!s) return;
    const id = uuid();
    keep({ id, kind: "year", hashes: [s.hash], value: v });
    setLabelled((n) => Math.max(n, 1)); setLast({ id, text: `Saved: ${v}` }); setStep("thanks");
  }

  // "I don't know" sends this photo to the back of THIS person's queue (it comes
  // back once they have seen the rest); everyone else is still asked it
  function shrug() {
    if (!s) return;
    void fetch("/api/skip", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: "story:" + s.hash }) }).catch(() => undefined);
  }
  // the skip is recorded while the next photo is shown: `after` leaves it out
  function skip() {
    shrug();
    next();
  }
  function next() {
    const n = s ? [...seen, s.hash] : seen;
    setSeen(n); setSingle(null); void load(n, null);
  }
  async function undo() {
    if (!last) return;
    await sending.current.get(last.id);
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
  return (
    <div className={step === "decade" ? "game picking" : "game"}>
      {step === "thanks" && labelled > 0 && <Confetti seed={labelled} />}
      <Shot src={img(s.hash)} alt="A family photo" />
      <div className="panel">
        {err && <p className="notice error" role="alert">{err}</p>}

        {step === "place" && (
          <PlacePicker key={s.hash} ask="Where was this taken?" places={s.places} cancel="I don't know"
            onCancel={s.needYear ? () => { void shrug(); setStep("decade"); } : skip} onPick={pickPlace} />
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
