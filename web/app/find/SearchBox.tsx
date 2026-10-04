"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "@/components/icons";

export default function SearchBox({ initial }: { initial: string }) {
  const [q, setQ] = useState(initial);
  const router = useRouter();
  return (
    <form role="search" className="stack" onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/find?q=${encodeURIComponent(q.trim())}`); }}>
      <label className="sr" htmlFor="q">What are you looking for?</label>
      <input id="q" className="field" type="search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Who, where, or what…" enterKeyHint="search" autoComplete="off" />
      <button className="btn block sun"><Search /> Search</button>
      {!initial && <p className="muted">Try <b>a name</b>, <b>a place</b>, <b>1998</b> or <b>a birthday party</b>. You can also tap the microphone on your keyboard and say it.</p>}
    </form>
  );
}
