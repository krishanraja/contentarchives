"use client";
import { useState } from "react";

// One step of signing in: a real form posted to /api/access, so a tap works
// before the page's script has arrived. Once it has, the button says at once
// that it heard (learning 81) and a second tap is not sent. The step rides in
// a hidden field, never on the button, so a button greyed out mid-send cannot
// drop it.
export default function Ask({ op, label, busy, tint = "", children, hidden = {}, pair = false }: {
  op: string; label: string; busy: string; tint?: string;
  children?: React.ReactNode; hidden?: Record<string, string>;
  pair?: boolean;          // a box and its button, side by side on a short screen
}) {
  const [on, setOn] = useState(false);
  return (
    <form method="post" action="/api/access" className={pair ? "gate-form gate-pair stack" : "gate-form stack"}
      onSubmit={(e) => { if (on) { e.preventDefault(); return; } setTimeout(() => setOn(true), 0); }}>
      <input type="hidden" name="op" value={op} />
      {Object.entries(hidden).map(([k, v]) => <input key={k} type="hidden" name={k} value={v} />)}
      {children}
      <button className={`btn block ${tint}`} disabled={on}>{on ? busy : label}</button>
    </form>
  );
}
