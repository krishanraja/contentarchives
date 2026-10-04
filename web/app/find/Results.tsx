"use client";
import Link from "next/link";
import { useState } from "react";
import type { Card } from "@/lib/data";

function label(c: Card) {
  if (c.year) return String(c.year);
  if (c.approx_year) return "about " + c.approx_year;
  return "";
}

export default function Results({ q, first, total }: { q: string; first: Card[]; total: number }) {
  const [cards, setCards] = useState(first);
  const [busy, setBusy] = useState(false);
  async function more() {
    setBusy(true);
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&offset=${cards.length}`).then((x) => x.json()).catch(() => null);
    if (r?.cards) setCards([...cards, ...r.cards]);
    setBusy(false);
  }
  return (
    <>
      <div className="grid">
        {cards.map((c, i) => (
          <Link key={c.hash} href={`/photo/${encodeURIComponent(c.hash)}?q=${encodeURIComponent(q)}`} aria-label={`Open photo${label(c) ? " from " + label(c) : ""}${c.place ? " in " + c.place : ""}`}>
            <img src={`/img/t/${encodeURIComponent(c.hash)}`} alt="" loading={i < 6 ? "eager" : "lazy"} decoding="async" />
            {(label(c) || c.media === "video") && <span className="badge">{c.media === "video" ? "Video" : label(c)}</span>}
          </Link>
        ))}
      </div>
      {cards.length < total && (
        <button className="btn block" onClick={more} disabled={busy}>{busy ? "Loading…" : "Show more photos"}</button>
      )}
    </>
  );
}
