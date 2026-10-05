"use client";
import { useRouter } from "next/navigation";
import { Search } from "@/components/icons";

// A real GET form (/find?q=...), so a search typed and tapped before the
// page's script arrives still works; with the script, the same form moves
// without a page load. The words are read from the form, never from React
// state, so nothing typed is lost when the script arrives. The example year is
// one this library actually has (a hard-coded 1998 found nothing here). The
// box and its button share one row, so the list below has the room.
export default function SearchBox({ initial, example = "" }: { initial: string; example?: string }) {
  const router = useRouter();
  return (
    <form role="search" className="stack" style={{ flex: "none", gap: 8 }} method="get" action="/find"
      onSubmit={(e) => {
        e.preventDefault();
        const q = String(new FormData(e.currentTarget).get("q") || "").trim();
        if (q) router.push(`/find?q=${encodeURIComponent(q)}`);
      }}>
      <label className="sr" htmlFor="q">What are you looking for?</label>
      <div className="searchrow">
        <input id="q" name="q" className="field" type="search" defaultValue={initial} key={initial}
          placeholder="Who, where, what…" enterKeyHint="search" autoComplete="off" />
        <button className="btn sun" aria-label="Search"><Search /> Search</button>
      </div>
      {!initial && <p className="muted hint">Try <b>a name</b>, <b>a place</b>{example ? <>, <b>{example}</b></> : null} or <b>a birthday</b>. You can also tap the microphone on your keyboard and say it.</p>}
    </form>
  );
}
