"use client";
import { useState } from "react";
import Fit from "./Fit";

// Roughly when, in two taps: a decade, then a year in it - or just the decade.
// A guess is fine. The same question wherever it is asked: "Where and when?"
// and a photograph's own "Change" (Krish, 2026-10-06: the date in a file is
// often the day it was scanned or copied, so it must be easy to put right).
export const DECADES = [1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020];

export default function YearPicker({ ask = "Roughly what year?", cancel, onCancel, onPick }: {
  ask?: string; cancel: string; onCancel: () => void;
  onPick: (value: string) => void;         // "1987", or "1980s" for just the decade
}) {
  const [decade, setDecade] = useState<number | null>(null);
  const now = new Date().getFullYear();
  if (decade === null) {
    return (
      <>
        <h2>{ask} <span className="muted" style={{ fontSize: 20, fontWeight: 400 }}>A guess is fine.</span></h2>
        <Fit label="Decades" className="chips when-grid">
          {DECADES.map((d) => <button key={d} type="button" className="chip" onClick={() => setDecade(d)}>{d}s</button>)}
        </Fit>
        <button type="button" className="btn block" onClick={onCancel}>{cancel}</button>
      </>
    );
  }
  return (
    <>
      <h2>Which year in the {decade}s?</h2>
      <Fit label="Years" className="chips when-grid years">
        {Array.from({ length: 10 }, (_, i) => decade + i).filter((y) => y <= now)
          .map((y) => <button key={y} type="button" className="chip" onClick={() => onPick(String(y))}>{y}</button>)}
      </Fit>
      <div className="row">
        <button type="button" className="btn" onClick={() => setDecade(null)}>‹ Other decades</button>
        <button type="button" className="btn mint" onClick={() => onPick(`${decade}s`)}>Just the {decade}s</button>
      </div>
    </>
  );
}

