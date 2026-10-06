"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Fit from "@/components/Fit";
import type { Card } from "@/lib/data";

function label(c: Card) {
  if (c.family_when) return /s$/.test(c.family_when) ? "the " + c.family_when : c.family_when;   // the family's year wins
  if (c.year) return String(c.year);
  if (c.approx_year) return "about " + c.approx_year;
  return "";
}

// As many photos as the screen holds, and "More photos" for the next lot: the
// page never scrolls. The next lot is fetched before it is asked for.
export default function Results({ q, first, total }: { q: string; first: Card[]; total: number }) {
  const [cards, setCards] = useState(first);
  const busy = useRef(false);
  const need = useCallback(async (n: number) => {
    if (busy.current) return;
    busy.current = true;
    let have = cards.length;
    const got: Card[] = [];
    while (have < Math.min(n, total)) {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&offset=${have}`).then((x) => x.json()).catch(() => null);
      if (!r?.cards?.length) break;
      got.push(...r.cards); have += r.cards.length;
    }
    if (got.length) setCards((c) => [...c, ...got.filter((g) => !c.some((x) => x.hash === g.hash))]);
    busy.current = false;
  }, [cards.length, q, total]);
  // the photo screen turns through these with Previous and Next
  useEffect(() => {
    try { sessionStorage.setItem("photos:" + q, JSON.stringify(cards.map((c) => c.hash))); } catch { /* private mode */ }
  }, [cards, q]);
  return (
    <Fit className="grid" cells label="Photos" more="More photos" total={total} need={need}>
      {cards.map((c, i) => (
        <Link key={c.hash} href={`/photo/${encodeURIComponent(c.hash)}?q=${encodeURIComponent(q)}`} aria-label={`Open photo${label(c) ? " from " + label(c) : ""}${c.place ? " in " + c.place : ""}`}>
          <img src={`/img/t/${encodeURIComponent(c.hash)}`} alt="" loading={i < 12 ? "eager" : "lazy"} decoding="async" />
          {(label(c) || c.media === "video") && <span className="badge">{c.media === "video" ? "Video" : label(c)}</span>}
        </Link>
      ))}
    </Fit>
  );
}
