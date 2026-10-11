"use client";
import { useEffect, useRef, useState } from "react";
import { Mic as MicIcon } from "./icons";

// Say it instead of typing it (Krish, 2026-10-11: be able to "say" what you
// are actually looking for). The browser's own speech recognition: Chrome on
// Android, Safari on iOS 14.5+. Where a browser has none, nothing is drawn -
// the box is still there to type in, and a keyboard's own microphone still
// works. What is heard goes into the box `target` and its form is sent.
type Rec = {
  lang: string; interimResults: boolean; maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null; onerror: (() => void) | null;
  start: () => void; stop: () => void;
};
type RecCtor = new () => Rec;

function recogniser(): RecCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecCtor; webkitSpeechRecognition?: RecCtor };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export default function Mic({ target, className = "btn mic" }: { target: string; className?: string }) {
  const [can, setCan] = useState(false);
  const [on, setOn] = useState(false);
  const rec = useRef<Rec | null>(null);
  useEffect(() => { setCan(!!recogniser()); return () => rec.current?.stop(); }, []);
  if (!can) return null;
  const listen = () => {
    if (on) { rec.current?.stop(); return; }
    const R = recogniser();
    if (!R) return;
    const r = new R();
    r.lang = navigator.language || "en-GB";
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      const said = Array.from(e.results).map((x) => x[0]?.transcript || "").join(" ").trim();
      const box = document.getElementById(target) as HTMLInputElement | null;
      if (!said || !box) return;
      box.value = said;
      box.form?.requestSubmit();
    };
    r.onend = () => setOn(false);
    r.onerror = () => setOn(false);
    rec.current = r;
    setOn(true);
    try { r.start(); } catch { setOn(false); }
  };
  return (
    <button type="button" className={on ? `${className} listening` : className} onClick={listen}
      aria-pressed={on} aria-label={on ? "Listening - tap to stop" : "Say it"}>
      <MicIcon />{on && <span className="mic-word" aria-hidden="true">Listening</span>}
    </button>
  );
}
