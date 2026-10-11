"use client";
import { useRouter } from "next/navigation";
import { Search } from "@/components/icons";
import Mic from "@/components/Mic";
import type { Media } from "@/lib/search";

// A real GET form (/find?q=...), so a search typed and tapped before the
// page's script arrives still works; with the script, the same form moves
// without a page load. The words are read from the form, never from React
// state, so nothing typed is lost when the script arrives. The example year is
// one this library actually has (a hard-coded 1998 found nothing here). The
// box and its button share one row, so the list below has the room.
//
// The type in force (Photos or Videos) rides along: a new search keeps it.
export default function SearchBox({ initial, example = "", type = null }: { initial: string; example?: string; type?: Media | null }) {
  const router = useRouter();
  return (
    <form role="search" className="stack" style={{ flex: "none", gap: 8 }} method="get" action="/find"
      onSubmit={(e) => {
        e.preventDefault();
        const q = String(new FormData(e.currentTarget).get("q") || "").trim();
        if (q) router.push(`/find?q=${encodeURIComponent(q)}${type ? `&type=${type}` : ""}`);
      }}>
      <label className="sr" htmlFor="q">What are you looking for?</label>
      {type && <input type="hidden" name="type" value={type} />}
      <div className="searchrow">
        <input id="q" name="q" className="field" type="search" defaultValue={initial} key={initial}
          placeholder="Type here" enterKeyHint="search" autoComplete="off" />
        <Mic target="q" />
        <button className="btn sun" aria-label="Search"><Search /> <span className="search-word">Search</span></button>
      </div>
      {!initial && <p className="muted hint">Try <b>a name</b>, <b>a place</b>{example ? <>, <b>{example}</b></> : null} or <b>a birthday</b>. You can also say it.</p>}
    </form>
  );
}
