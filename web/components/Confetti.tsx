"use client";
const COLOURS = ["#ffc93c", "#ff6a45", "#ff9ccf", "#4fe0a5", "#7cc4ff", "#b9a3ff"];

// A small celebration. Hidden entirely for anyone who asks their phone for
// less motion (globals.css).
export default function Confetti({ seed }: { seed: number }) {
  const bits = Array.from({ length: 36 }, (_, i) => {
    const r = Math.sin(seed * 999 + i * 77) * 10000;
    const f = r - Math.floor(r);
    return (
      <i key={i} style={{
        left: `${(i * 2.9 + f * 20) % 100}%`,
        background: COLOURS[i % COLOURS.length],
        animationDelay: `${(f * 0.35).toFixed(2)}s`,
      }} />
    );
  });
  return <div className="confetti" aria-hidden="true">{bits}</div>;
}
