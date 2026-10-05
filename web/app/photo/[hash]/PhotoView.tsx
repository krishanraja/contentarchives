"use client";
import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import Shot from "@/components/Shot";
import { Back, Eye, Pin, Share } from "@/components/icons";

type P = { hash: string; alt: string; people: string[]; where: string; when: string | null; what: string | null; video: boolean; needs: boolean };

// The photo fills the screen; one line says who, one says where and when, and
// "About this photo" turns the picture over to everything we know about it.
// Nothing scrolls (Krish, 2026-10-05): a long description is set smaller to
// fit, never below the floor's 16px, and only then shortened.
export default function PhotoView({ p, back }: { p: P; back: string }) {
  const [about, setAbout] = useState(false);
  const [sure, setSure] = useState(false);
  const [hidden, setHidden] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const what = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const b = box.current;
    if (!about || !b) return;
    const fit = () => {
      const w = what.current;
      if (w) w.style.webkitLineClamp = "";
      for (let px = 21; px >= 16; px--) {
        b.style.fontSize = `${px}px`;
        if (b.scrollHeight <= b.clientHeight + 1) return;
      }
      if (w) {   // still too long at 16px: as many lines of the description as there is room for
        const lh = parseFloat(getComputedStyle(w).lineHeight) || 22;
        const over = b.scrollHeight - b.clientHeight;
        w.style.webkitLineClamp = String(Math.max(1, Math.floor((w.offsetHeight - over) / lh)));
      }
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(b);
    let live = true;
    document.fonts?.ready.then(() => { if (live) fit(); });
    return () => { live = false; ro.disconnect(); };
  }, [about, sure]);

  async function share() {
    try {
      const blob = await fetch(`/img/v/${encodeURIComponent(p.hash)}`).then((r) => r.blob());
      const file = new File([blob], "family-photo.jpg", { type: "image/jpeg" });
      if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file] }); return; }
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "family-photo.jpg"; a.click();
    } catch { /* closed the share sheet */ }
  }
  async function hide() {
    const r = await fetch("/api/hide", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hash: p.hash }) });
    if (r.ok) setHidden(true);
  }

  const who = p.people.length ? p.people.join(", ") : "Nobody named yet";
  const whereWhen = [p.where, p.when].filter(Boolean).join(" · ") || "Where and when: not known yet";
  return (
    <div className="game">
      {!about ? (
        <Shot src={`/img/v/${encodeURIComponent(p.hash)}`} alt={p.alt} />
      ) : (
        <div className="card about">
          {hidden ? <p className="notice">This photo is now hidden for everyone. Thank you.</p> : sure ? (
            <>
              <p><b>Hide this photo for everyone?</b> Krish can bring it back if it was a mistake.</p>
              <div className="row" style={{ flex: "none" }}>
                <button className="btn" onClick={() => setSure(false)}>No</button>
                <button className="btn tomato" onClick={hide}>Yes, hide it</button>
              </div>
            </>
          ) : (
            <>
              {/* the words take the room the two buttons leave them, set smaller to fit */}
              <div className="about-text" ref={box}>
                <div><h3>Who</h3><p>{p.people.length ? who : <span className="muted">Nobody named yet</span>}</p></div>
                <div><h3>Where</h3><p>{p.where || <span className="muted">Not known yet</span>}</p></div>
                <div><h3>When</h3><p>{p.when || <span className="muted">Not known yet</span>}</p></div>
                {p.video && <p>This is a video; the picture is a still from it.</p>}
                {p.what && <div><h3>What</h3><p className="what" ref={what}>{p.what}</p></div>}
              </div>
              <div className="stack" style={{ gap: 8, flex: "none" }}>
                {p.needs && <Link className="btn block mint small" href={`/story?photo=${encodeURIComponent(p.hash)}`}><Pin /> I know where or when</Link>}
                <button className="btn block quiet small" onClick={() => setSure(true)}><Eye /> This photo shouldn't be here</button>
              </div>
            </>
          )}
        </div>
      )}
      <div className="panel">
        {!about && (
          <div className="caption">
            <p><b>{who}</b></p>
            <p>{p.video ? "A still from a video · " : ""}{whereWhen}</p>
          </div>
        )}
        <button className="btn block grape" onClick={() => { setAbout(!about); setSure(false); }}>
          {about ? "Show the photo" : "About this photo"}
        </button>
        <div className="row">
          <Link className="btn" href={back}><Back /> Back to photos</Link>
          <button className="btn sky" onClick={share}><Share /> Send</button>
        </div>
      </div>
    </div>
  );
}
