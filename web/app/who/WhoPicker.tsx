"use client";
import { useState } from "react";
import Fit from "@/components/Fit";

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
  const nameForm = (
    <form className="card nameform" method="post" action="/api/who" onSubmit={pick} style={{ flex: "none" }}>
      <label className="big" htmlFor="me">Your first name</label>
      <input id="me" name="name" className="field" autoComplete="given-name" autoCapitalize="words" enterKeyHint="done" placeholder="Your first name" minLength={2} required />
      <button className="btn block mint">That's me</button>
    </form>
  );
  // No names set up: the family is not a list we know, so just ask - one box,
  // no extra tap. Names set up (players): one tap each, and "Someone else".
  // A long family turns its names like pages; the screen never scrolls.
  if (!names.length) return nameForm;
  return (
    <>
      <Fit className="stack" label="Our names" more="More names" turn="btn block">
        {names.map((n, i) => (
          <form key={n} method="post" action="/api/who" onSubmit={pick}>
            <input type="hidden" name="name" value={n} />
            <button className={`btn block ${TINTS[i % TINTS.length]}`}>{n}</button>
          </form>
        ))}
      </Fit>
      <details className="stack" style={{ flex: "none" }}>
        <summary className="btn block">Someone else</summary>
        {nameForm}
      </details>
    </>
  );
}
