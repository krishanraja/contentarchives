"use client";
import { useState } from "react";

const SAID: Record<string, string> = {
  wrong: "That's not it. Try again, or ask Krish.",
  locked: "Too many tries. Please wait an hour, or ask Krish.",
};

// A real form (method + action + a named field), so the code works even when it
// is typed and tapped before the page's script has arrived; once it has, the
// same form is handled here without a page load. The field is NOT tied to React
// state, so a late-arriving script can never wipe what was already typed.
export default function GateForm({ said = "" }: { said?: string }) {
  const [msg, setMsg] = useState(SAID[said] || "");
  const [busy, setBusy] = useState(false);
  async function go(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code") || "");
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
    <form onSubmit={go} method="post" action="/api/gate" className="card" style={{ flex: "none" }}>
      <label className="big" htmlFor="code">Enter the family code</label>
      <input id="code" name="code" className="field"
        autoComplete="off" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
        enterKeyHint="go" placeholder="Family code" aria-describedby="gate-msg" />
      <button className="btn block tomato" disabled={busy}>{busy ? "Opening…" : "Open"}</button>
      <p id="gate-msg" role="alert" className={msg ? "notice error" : "sr"}>{msg}</p>
    </form>
  );
}
