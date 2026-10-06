"use client";
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Clip from "@/components/Clip";
import Shot from "@/components/Shot";
import Squeeze from "@/components/Squeeze";
import Undo from "@/components/Undo";
import YearPicker from "@/components/YearPicker";
import { whenLabel } from "@/lib/when";
import { send, uuid } from "@/components/outbox";
import { Eye, Pin, Share } from "@/components/icons";

type P = { hash: string; alt: string; people: string[]; where: string; when: string | null; what: string | null; video: boolean;
  play: "ok" | "unplayable" | null; needs: boolean; sameDay: string[]; dayText: string | null };
type Mode = "view" | "about" | "when" | "same";

// The photo fills the screen. Under it: who is in it, where, and WHEN - the
// year is a button, because the date in a file is often the day it was
// scanned or copied (Krish, 2026-10-06), and putting it right must take two
// taps: a decade, a year. Previous and Next turn through the photos the
// search found, without going back to them each time. "About this photo"
// turns the picture over to everything we know about it. Nothing scrolls
// (Krish, 2026-10-05). A video judged whole plays in the picture's place.
export default function PhotoView({ p, q }: { p: P; q: string }) {
  const [mode, setMode] = useState<Mode>("view");
  const [failed, setFailed] = useState(false);
  const fail = useCallback(() => setFailed(true), []);
  const [sure, setSure] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [when, setWhen] = useState(p.when);
  const [last, setLast] = useState<{ id: string; text: string; was: string | null } | null>(null);
  const [err, setErr] = useState("");
  const [nav, setNav] = useState<{ prev: string | null; next: string | null } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const what = useRef<HTMLParagraphElement>(null);
  const about = mode === "about";

  // the photos the search found, as the results screen left them on this phone
  useEffect(() => {
    if (!q) return;
    try {
      const list = JSON.parse(sessionStorage.getItem("photos:" + q) || "null");
      const i = Array.isArray(list) ? list.indexOf(p.hash) : -1;
      if (i >= 0) {
        setNav({ prev: list[i - 1] ?? null, next: list[i + 1] ?? null });
        if (list[i + 1]) new Image().src = `/img/v/${encodeURIComponent(list[i + 1])}`;   // the next one is ready
      }
    } catch { /* no list: no turning */ }
  }, [q, p.hash]);

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

  function pick(v: string) {
    if (p.sameDay.length) { setPicked(v); setMode("same"); } else void saveYear(v, [p.hash]);
  }
  async function saveYear(v: string, hashes: string[]) {
    const id = uuid();
    const r = await send({ id, kind: "year", hashes, value: v });
    if (!r.ok && r.error && !r.error.startsWith("offline")) { setErr(r.error); return; }
    const n = r.labelled ?? hashes.length;
    setLast({ id, was: when, text: `Saved: ${whenLabel(v)}${n > 1 ? ` for ${n} photos` : ""}` });
    setWhen(whenLabel(v)); setErr(""); setMode("view");
  }
  async function undo() {
    if (!last) return;
    await fetch("/api/answers/undo", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: last.id }) }).catch(() => undefined);
    setWhen(last.was); setLast(null);
  }

  const who = p.people.length ? p.people.join(", ") : "Nobody named yet";
  const plays = p.video && p.play === "ok" && !failed;
  const noun = p.video ? "video" : "photo";
  const still = !p.video ? null : plays ? null
    : failed || p.play === "unplayable" ? "This video can't play on this phone; the picture is a still from it."
    : "This video isn't ready to play yet; the picture is a still from it.";
  // Previous and Next keep their words while there is room; on a cramped
  // screen they become arrows beside About and Send (Squeeze, globals.css)
  const turn = (h: string | null, way: "prev" | "next") => {
    const name = way === "prev" ? "Previous photo" : "Next photo";
    const body = way === "prev"
      ? <><span aria-hidden="true">‹</span><span className="word" aria-hidden="true">Previous</span></>
      : <><span className="word" aria-hidden="true">Next</span><span aria-hidden="true">›</span></>;
    return h
      ? <Link className={`btn ${way}`} aria-label={name} replace href={`/photo/${encodeURIComponent(h)}?q=${encodeURIComponent(q)}`}>{body}</Link>
      : <button type="button" className={`btn ${way}`} aria-label={name} disabled>{body}</button>;
  };
  const turns = !!(q && nav);

  return (
    <div className={mode === "when" ? "game picking" : "game"}>
      {mode !== "about" ? (plays && mode === "view"
        ? <Clip hash={p.hash} alt={p.alt} onFail={fail} />
        : <Shot src={`/img/v/${encodeURIComponent(p.hash)}`} alt={p.alt} />
      ) : (
        <div className="card about">
          {hidden ? <p className="notice">This {noun} is now hidden for everyone. Thank you.</p> : sure ? (
            <>
              <p><b>Hide this {noun} for everyone?</b> Krish can bring it back if it was a mistake.</p>
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
                <div><h3>When</h3><p>{when || <span className="muted">Not known yet</span>}</p></div>
                {still && <p>{still}</p>}
                {p.what && <div><h3>What</h3><p className="what" ref={what}>{p.what}</p></div>}
              </div>
              <div className="stack" style={{ gap: 8, flex: "none" }}>
                {p.needs && !p.where && <Link className="btn block mint small" href={`/story?photo=${encodeURIComponent(p.hash)}`}><Pin /> I know where it was</Link>}
                <button className="btn block quiet small" onClick={() => setSure(true)}><Eye /> This {noun} shouldn&apos;t be here</button>
              </div>
            </>
          )}
        </div>
      )}
      <Squeeze className="panel photo-panel" levels={4}>
        {err && <p className="notice error" role="alert">{err}</p>}
        {mode === "when" && (
          <YearPicker ask={`When was this ${noun} taken?`} cancel="Cancel" onCancel={() => setMode("view")} onPick={pick} />
        )}
        {mode === "same" && picked && (
          <>
            <h2>Change the {p.sameDay.length} other {p.sameDay.length === 1 ? "photo" : "photos"}
              {p.dayText ? ` dated ${p.dayText}` : " from that day"} to {whenLabel(picked)} too?</h2>
            <div className="strip">{p.sameDay.slice(0, 4).map((h) => <img key={h} src={`/img/t/${encodeURIComponent(h)}`} alt="" />)}</div>
            <div className="row">
              <button className="btn" onClick={() => saveYear(picked, [p.hash])}>Just this one</button>
              <button className="btn mint" onClick={() => saveYear(picked, [p.hash, ...p.sameDay])}>Yes, all {p.sameDay.length + 1}</button>
            </div>
          </>
        )}
        {mode === "view" && (
          <>
            <div className="caption">
              <p><b>{who}</b></p>
              <p>{plays ? "A video · " : p.video ? "A still from a video · " : ""}{p.where || "Place not known yet"}</p>
            </div>
            <button type="button" className="btn block when" onClick={() => setMode("when")}
              aria-label={when ? `Taken ${when}. Change the year` : "Year not known. Add the year"}>
              <span className="when-date">{when || "Year not known"}</span>
              <span className="when-do">{when ? "Change" : "Add"}</span>
            </button>
          </>
        )}
        {(mode === "view" || mode === "about") && (
          <div className={turns ? "turnrow turns" : "turnrow"}>
            {turns && turn(nav!.prev, "prev")}
            {turns && turn(nav!.next, "next")}
            <button className="btn grape about-btn" onClick={() => { setMode(about ? "view" : "about"); setSure(false); }}>
              {about ? <>Show<span className="word"> the {noun}</span></> : <>About<span className="word"> this {noun}</span></>}
            </button>
            <button className="btn sky send" onClick={share}><Share /> Send</button>
          </div>
        )}
        {last && mode === "view" && <Undo text={last.text} onUndo={undo} onDone={() => setLast(null)} />}
      </Squeeze>
    </div>
  );
}

