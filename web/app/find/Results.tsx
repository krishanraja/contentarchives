"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Fit from "@/components/Fit";
import type { Card } from "@/lib/data";
import { clock, listKey, type Media } from "@/lib/search";

function label(c: Card) {
  if (c.family_when) return /s$/.test(c.family_when) ? "the " + c.family_when : c.family_when;   // the family's year wins
  if (c.year) return String(c.year);
  if (c.approx_year) return "about " + c.approx_year;
  return "";
}

// "Video, 1 minute 23" - what the play mark says out loud
function spoken(seconds: number | null) {
  if (seconds === null || seconds === undefined) return "Video";
  const m = Math.floor(seconds / 60), s = Math.round(seconds % 60);
  return `Video, ${m ? `${m} minute${m === 1 ? "" : "s"} ` : ""}${s} second${s === 1 ? "" : "s"}`;
}

// As many as the screen holds, and "More" for the next lot: the
// page never scrolls. The next lot is fetched before it is asked for. A video
// carries a play mark and its length, and keeps its year (Krish, 2026-10-11:
// "see if an individual piece of content is a video or a photo").
export default function Results({ q, type, first, total }: { q: string; type: Media | null; first: Card[]; total: number }) {
  const tq = type ? `&type=${type}` : "";
  const [cards, setCards] = useState(first);
  const busy = useRef(false);
  const need = useCallback(async (n: number) => {
    if (busy.current) return;
    busy.current = true;
    let have = cards.length;
    const got: Card[] = [];
    while (have < Math.min(n, total)) {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&offset=${have}${tq}`).then((x) => x.json()).catch(() => null);
      if (!r?.cards?.length) break;
      got.push(...r.cards); have += r.cards.length;
    }
    if (got.length) setCards((c) => [...c, ...got.filter((g) => !c.some((x) => x.hash === g.hash))]);
    busy.current = false;
  }, [cards.length, q, tq, total]);
  // the photo screen turns through these with Previous and Next
  useEffect(() => {
    try { sessionStorage.setItem(listKey(q, type), JSON.stringify(cards.map((c) => c.hash))); } catch { /* private mode */ }
  }, [cards, q, type]);
  return (
    <Fit className="grid" cells label={type === "video" ? "Videos" : type === "photo" ? "Photos" : "Photos and videos"} more="More" total={total} need={need}>
      {cards.map((c, i) => (
        <Link key={c.hash} href={`/photo/${encodeURIComponent(c.hash)}?q=${encodeURIComponent(q)}${tq}`}
          aria-label={`Open ${c.media === "video" ? spoken(c.seconds).replace(/^Video/, "video") : "photo"}${label(c) ? " from " + label(c) : ""}${c.place ? " in " + c.place : ""}`}>
          <img src={`/img/t/${encodeURIComponent(c.hash)}`} alt="" loading={i < 12 ? "eager" : "lazy"} decoding="async" />
          {label(c) && <span className="badge">{label(c)}</span>}
          {c.media === "video" && (
            <span className="vmark" aria-hidden="true">
              <span className="tri" />{clock(c.seconds) && <span className="len">{clock(c.seconds)}</span>}
            </span>
          )}
        </Link>
      ))}
    </Fit>
  );
}
