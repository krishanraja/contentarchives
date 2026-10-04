"use client";
import { useState } from "react";

export default function GateForm() {
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) { setMsg("Type the family code first."); return; }
    setBusy(true); setMsg("");
    const r = await fetch("/api/gate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ code }) }).catch(() => null);
    setBusy(false);
    if (r?.ok) { window.location.href = "/who"; return; }
    if (r?.status === 429) setMsg("Too many tries. Please wait an hour, or ask Krish.");
    else if (!r) setMsg("No internet connection. Try again in a moment.");
    else setMsg("That's not it. Try again, or ask Krish.");
  }
  return (
    <form onSubmit={go} className="card">
      <label className="big" htmlFor="code">Enter the family code</label>
      <input id="code" className="field" value={code} onChange={(e) => setCode(e.target.value)}
        autoComplete="off" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
        enterKeyHint="go" placeholder="Family code" aria-describedby="gate-msg" />
      <button className="btn block tomato" disabled={busy}>{busy ? "Opening…" : "Open"}</button>
      <p id="gate-msg" role="alert" className={msg ? "notice error" : "sr"}>{msg}</p>
    </form>
  );
}
