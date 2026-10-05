"use client";
import { useState } from "react";

const TINTS = ["sun", "pink", "mint", "sky", "grape", "tomato"];

// Every choice is a real form posting to /api/who, so a tap made before the
// page's script has arrived still works; once it has, the same tap is handled
// here without a page load. "Someone else" is the browser's own disclosure, so
// it opens with or without the script.
export default function WhoPicker({ names }: { names: string[] }) {
  const [busy, setBusy] = useState(false);
  async function pick(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const name = String(new FormData(e.currentTarget).get("name") || "").trim();
    if (name.length < 2 || busy) return;
    setBusy(true);
    const r = await fetch("/api/who", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name }) });
    if (r.ok) window.location.href = "/";
    else setBusy(false);
  }
  return (
    <div className="stack">
      {names.map((n, i) => (
        <form key={n} method="post" action="/api/who" onSubmit={pick}>
          <input type="hidden" name="name" value={n} />
          <button className={`btn block ${TINTS[i % TINTS.length]}`}>{n}</button>
        </form>
      ))}
      <details className="stack">
        <summary className="btn block">Someone else</summary>
        <form className="card" method="post" action="/api/who" onSubmit={pick}>
          <label className="big" htmlFor="me">Your name</label>
          <input id="me" name="name" className="field" autoComplete="given-name" autoCapitalize="words" enterKeyHint="done" placeholder="Your first name" minLength={2} required />
          <button className="btn block mint">That's me</button>
        </form>
      </details>
    </div>
  );
}
