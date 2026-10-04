"use client";
import { useEffect, useState } from "react";

// After every answer: what was saved, and a big Undo. It stays 12 seconds -
// long enough to read twice - and the server allows undo for ten minutes.
export default function Undo({ text, onUndo, onDone }: { text: string; onUndo: () => void; onDone: () => void }) {
  const [left, setLeft] = useState(12);
  useEffect(() => {
    if (left <= 0) { onDone(); return; }
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left, onDone]);
  return (
    <div className="undo" role="status" aria-live="polite">
      <span>{text}</span>
      <button className="btn small" onClick={onUndo}>Undo</button>
    </div>
  );
}
