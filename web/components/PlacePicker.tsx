"use client";
import { useEffect, useState } from "react";
import Fit from "./Fit";
import { close, exact } from "@/lib/spelling";

// Where, in one or two taps: the places the family already uses, as big
// chips, or typed. A place spelled the way the family already spells it IS
// that place; a near miss ("Naintal") is asked about - "Did you mean
// Nainital?" - and never changed without a tap. The same question wherever
// it is asked: "Where and when?" and a photograph's own "Change".
export default function PlacePicker({ ask, places, cancel, onCancel, onPick }: {
  ask: string; places?: string[];          // the chips; the family's most used places when not given
  cancel: string; onCancel: () => void; onPick: (place: string) => void;
}) {
  const [known, setKnown] = useState<string[]>([]);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [meant, setMeant] = useState<string[] | null>(null);
  useEffect(() => {
    fetch("/api/names").then((r) => r.json()).then((j) => setKnown(j.places || [])).catch(() => undefined);
  }, []);
  const chips = places ?? known.slice(0, 8);
  const typed = text.trim().replace(/\s+/g, " ");

  function save() {
    if (typed.length < 2) return;
    const all = [...new Set([...chips, ...known])];
    const same = exact(typed, all);
    if (same) { onPick(same); return; }
    const near = close(typed, all);
    if (near.length) { setMeant(near); return; }
    onPick(typed);
  }

  if (meant) {
    return (
      <>
        <h2>Did you mean {meant.length === 1 ? `${meant[0]}?` : "one of these?"}</h2>
        <Fit label="Places we already know" more="More places">
          {meant.map((p) => <button key={p} type="button" className="chip" onClick={() => onPick(p)}>{p}</button>)}
        </Fit>
        <div className="row">
          <button type="button" className="btn" onClick={() => setMeant(null)}>Change what I typed</button>
          <button type="button" className="btn" onClick={() => onPick(typed)}>No, save “{typed}”</button>
        </div>
      </>
    );
  }
  if (typing) {
    return (
      <form className="contents" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <h2>{ask}</h2>
        <label className="sr" htmlFor="pl">The place</label>
        <input id="pl" className="field" value={text} onChange={(e) => setText(e.target.value)} autoFocus
          placeholder="A town, a house, a country…" autoCapitalize="words" enterKeyHint="done" />
        <div className="row">
          <button type="button" className="btn" onClick={onCancel}>{cancel}</button>
          <button className="btn mint">Save this place</button>
        </div>
      </form>
    );
  }
  return (
    <>
      <h2>{ask}</h2>
      {chips.length > 0 && (
        <Fit label="Places" more="More places">
          {chips.map((p) => <button key={p} type="button" className="chip" onClick={() => onPick(p)}>{p}</button>)}
        </Fit>
      )}
      <div className="row">
        <button type="button" className="btn sky" onClick={() => setTyping(true)}>{chips.length ? "Somewhere else" : "Type the place"}</button>
        <button type="button" className="btn" onClick={onCancel}>{cancel}</button>
      </div>
    </>
  );
}
