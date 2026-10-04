"use client";
import { useState } from "react";

const TINTS = ["sun", "pink", "mint", "sky", "grape", "tomato"];

export default function WhoPicker({ names }: { names: string[] }) {
  const [other, setOther] = useState(false);
  const [name, setName] = useState("");
  async function pick(n: string) {
    const r = await fetch("/api/who", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: n }) });
    if (r.ok) window.location.href = "/";
  }
  return (
    <div className="stack">
      {names.map((n, i) => (
        <button key={n} className={`btn block ${TINTS[i % TINTS.length]}`} onClick={() => pick(n)}>{n}</button>
      ))}
      {!other ? (
        <button className="btn block" onClick={() => setOther(true)}>Someone else</button>
      ) : (
        <form className="card" onSubmit={(e) => { e.preventDefault(); if (name.trim().length > 1) pick(name); }}>
          <label className="big" htmlFor="me">Your name</label>
          <input id="me" className="field" value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" autoCapitalize="words" enterKeyHint="done" placeholder="Your first name" />
          <button className="btn block mint">That's me</button>
        </form>
      )}
    </div>
  );
}
