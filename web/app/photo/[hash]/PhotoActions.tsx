"use client";
import Link from "next/link";
import { useState } from "react";
import { Eye, Pin, Share } from "@/components/icons";

export default function PhotoActions({ hash, needs }: { hash: string; needs: boolean }) {
  const [hidden, setHidden] = useState(false);
  const [sure, setSure] = useState(false);
  async function share() {
    try {
      const blob = await fetch(`/img/v/${encodeURIComponent(hash)}`).then((r) => r.blob());
      const file = new File([blob], "family-photo.jpg", { type: "image/jpeg" });
      if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file] }); return; }
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "family-photo.jpg"; a.click();
    } catch { /* closed the share sheet */ }
  }
  async function hide() {
    const r = await fetch("/api/hide", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hash }) });
    if (r.ok) setHidden(true);
  }
  if (hidden) return <p className="notice">This photo is now hidden for everyone. Thank you.</p>;
  return (
    <div className="stack">
      <button className="btn block sky" onClick={share}><Share /> Send this photo</button>
      {needs && <Link className="btn block mint" href={`/story?photo=${encodeURIComponent(hash)}`}><Pin /> I know where or when this was</Link>}
      {!sure ? (
        <button className="btn block quiet" onClick={() => setSure(true)}><Eye /> This photo shouldn't be here</button>
      ) : (
        <div className="card">
          <p><b>Hide this photo for everyone?</b> Krish can bring it back if it was a mistake.</p>
          <div className="row">
            <button className="btn" onClick={() => setSure(false)}>No</button>
            <button className="btn tomato" onClick={hide}>Yes, hide it</button>
          </div>
        </div>
      )}
    </div>
  );
}
