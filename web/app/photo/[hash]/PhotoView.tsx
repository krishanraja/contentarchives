"use client";
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Clip from "@/components/Clip";
import Fit from "@/components/Fit";
import PlacePicker from "@/components/PlacePicker";
import Shot from "@/components/Shot";
import Squeeze from "@/components/Squeeze";
import Undo from "@/components/Undo";
import YearPicker from "@/components/YearPicker";
import { whenLabel } from "@/lib/when";
import { close, exact } from "@/lib/spelling";
import { send, uuid } from "@/components/outbox";
import { Eye, Share } from "@/components/icons";

type P = { hash: string; alt: string; people: string[]; where: string; when: string | null; what: string | null; video: boolean;
  play: "ok" | "unplayable" | null; sameDay: string[]; sameDayPlace: string[]; dayText: string | null };
type Mode = "view" | "about" | "when" | "sameWhen" | "where" | "sameWhere" | "who" | "add";
type Last = { id: string; text: string; undo: () => void };

// The photo fills the screen. Under it, three cards - WHO is in it, WHERE,
// WHEN - and each one is a button that puts it right (Krish, 2026-10-06:
// "everything needs to be 10x more intuitive"; a file's date is often the day
// it was scanned, a library's place a guess, a face's name a mistake). The
// family's answer wins everywhere, and only on this photograph. Previous and
// Next turn through the photos the search found. Nothing scrolls (2026-10-05):
// on a cramped screen the panel squeezes (components/Squeeze, globals.css).
export default function PhotoView({ p, q }: { p: P; q: string }) {
  const [mode, setMode] = useState<Mode>("view");
  const [failed, setFailed] = useState(false);
  const fail = useCallback(() => setFailed(true), []);
  const [sure, setSure] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [when, setWhen] = useState(p.when);
  const [where, setWhere] = useState(p.where);
  const [people, setPeople] = useState(p.people);
  const [last, setLast] = useState<Last | null>(null);
  const [err, setErr] = useState("");
  const [nav, setNav] = useState<{ prev: string | null; next: string | null } | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [typed, setTyped] = useState("");
  const [meant, setMeant] = useState<string[] | null>(null);
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
  useEffect(() => {
    if (mode !== "add" || names.length) return;
    fetch("/api/names").then((r) => r.json()).then((j) => setNames(j.people || [])).catch(() => undefined);
  }, [mode, names.length]);

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

  // one answer, saved even with no signal (the outbox), and one Undo for it
  async function answer(kind: string, value: string, hashes: string[], text: string, put: () => void, back: () => void) {
    const id = uuid();
    const r = await send({ id, kind, hashes, value });
    if (!r.ok && r.error && !r.error.startsWith("offline")) { setErr(r.error); return false; }
    put(); setErr(""); setMode("view");
    setLast({ id, text, undo: back });
    return true;
  }
  async function undo() {
    if (!last) return;
    await fetch("/api/answers/undo", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: last.id }) }).catch(() => undefined);
    last.undo(); setLast(null);
  }

  const saveYear = (v: string, hashes: string[]) => {
    const was = when;
    return answer("year", v, hashes, `Saved: ${whenLabel(v)}${hashes.length > 1 ? ` for ${hashes.length} photos` : ""}`,
      () => setWhen(whenLabel(v)), () => setWhen(was));
  };
  const savePlace = (v: string, hashes: string[]) => {
    const was = where;
    return answer("place", v, hashes, `Saved: ${v}${hashes.length > 1 ? ` for ${hashes.length} photos` : ""}`,
      () => setWhere(v), () => setWhere(was));
  };
  const takeOff = (name: string) => {
    const was = people;
    return answer("out", name, [p.hash], `Taken off: ${name}`,
      () => setPeople((x) => x.filter((n) => n !== name)), () => setPeople(was));
  };
  const addPerson = (name: string) => {
    const was = people;
    return answer("in", name, [p.hash], `Added: ${name}`, () => {
      setPeople((x) => (x.includes(name) ? x : [...x, name].sort())); setTyped(""); setMeant(null);
    }, () => setPeople(was));
  };
  // a name spelled the way the family already spells it IS that person; a near
  // miss is asked about. The family's names are fetched first if they are not
  // here yet - a fast typist must not slip a misspelling past the question.
  async function typedName() {
    const v = typed.trim().replace(/\s+/g, " ");
    if (v.length < 2) return;
    let all = names;
    if (!all.length) {
      all = await fetch("/api/names").then((r) => r.json()).then((j) => j.people || []).catch(() => []);
      setNames(all);
    }
    const same = exact(v, all);
    if (same) { void addPerson(same); return; }
    const near = close(v, all);
    if (near.length) { setMeant(near); return; }
    void addPerson(v);
  }

  const who = people.length ? people.join(", ") : "Nobody named yet";
  const plays = p.video && p.play === "ok" && !failed;
  const noun = p.video ? "video" : "photo";
  const still = !p.video ? null : plays ? null
    : failed || p.play === "unplayable" ? "This video can't play on this phone; the picture is a still from it."
    : "This video isn't ready to play yet; the picture is a still from it.";
  // Previous and Next keep their words while there is room; on a cramped
  // screen they become arrows beside About and Send
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
  const fact = (k: string, v: string, go: Mode, label: string) => (
    <button type="button" className={`btn fact fact-${k.toLowerCase()}`} onClick={() => { setMode(go); setErr(""); }} aria-label={label}>
      <span className="fact-k" aria-hidden="true">{k} <span className="fact-do">Change</span></span>
      <span className="fact-v" aria-hidden="true">{v}</span>
    </button>
  );
  const picking = mode === "when" || mode === "where" || mode === "who" || mode === "add";

  return (
    <div className={picking ? "game picking" : "game"}>
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
              {/* the words take the room the button leaves them, set smaller to fit */}
              <div className="about-text" ref={box}>
                <div><h3>Who</h3><p>{people.length ? who : <span className="muted">Nobody named yet</span>}</p></div>
                <div><h3>Where</h3><p>{where || <span className="muted">Not known yet</span>}</p></div>
                <div><h3>When</h3><p>{when || <span className="muted">Not known yet</span>}</p></div>
                {still && <p>{still}</p>}
                {p.what && <div><h3>What</h3><p className="what" ref={what}>{p.what}</p></div>}
              </div>
              <div className="stack" style={{ gap: 8, flex: "none" }}>
                <button className="btn block quiet small" onClick={() => setSure(true)}><Eye /> This {noun} shouldn&apos;t be here</button>
              </div>
            </>
          )}
        </div>
      )}
      <Squeeze className="panel photo-panel" levels={4}>
        {err && <p className="notice error" role="alert">{err}</p>}

        {mode === "when" && (
          <YearPicker ask={`When was this ${noun} taken?`} cancel="Cancel" onCancel={() => setMode("view")}
            onPick={(v) => { if (p.sameDay.length) { setPicked(v); setMode("sameWhen"); } else void saveYear(v, [p.hash]); }} />
        )}
        {mode === "sameWhen" && picked && (
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

        {mode === "where" && (
          <PlacePicker ask={`Where was this ${noun} taken?`} cancel="Cancel" onCancel={() => setMode("view")}
            onPick={(v) => { if (p.sameDayPlace.length) { setPicked(v); setMode("sameWhere"); } else void savePlace(v, [p.hash]); }} />
        )}
        {mode === "sameWhere" && picked && (
          <>
            <h2>Was the {p.sameDayPlace.length} other {p.sameDayPlace.length === 1 ? "photo" : "photos"}
              {p.dayText ? ` dated ${p.dayText}` : " from that day"} in {picked} too?</h2>
            <div className="strip">{p.sameDayPlace.slice(0, 4).map((h) => <img key={h} src={`/img/t/${encodeURIComponent(h)}`} alt="" />)}</div>
            <div className="row">
              <button className="btn" onClick={() => savePlace(picked, [p.hash])}>Just this one</button>
              <button className="btn mint" onClick={() => savePlace(picked, [p.hash, ...p.sameDayPlace])}>Yes, all {p.sameDayPlace.length + 1}</button>
            </div>
          </>
        )}

        {mode === "who" && (
          <>
            <h2>Who is in this {noun}? <span className="muted" style={{ fontSize: 20, fontWeight: 400 }}>
              {people.length ? "Tap a name that's wrong to take it off." : "Nobody is named yet."}</span></h2>
            {people.length > 0 && (
              <Fit label="People in it" more="More names">
                {people.map((n) => (
                  <button key={n} type="button" className="chip off" aria-label={`Take ${n} off this ${noun}`} onClick={() => takeOff(n)}>
                    {n} <span aria-hidden="true">✕</span>
                  </button>
                ))}
              </Fit>
            )}
            <div className="row">
              <button type="button" className="btn sky" onClick={() => setMode("add")}>Add someone</button>
              <button type="button" className="btn" onClick={() => setMode("view")}>Done</button>
            </div>
          </>
        )}
        {mode === "add" && (meant ? (
          <>
            <h2>Did you mean {meant.length === 1 ? `${meant[0]}?` : "one of these?"}</h2>
            <Fit label="Names we already know" more="More names">
              {meant.map((n) => <button key={n} type="button" className="chip" onClick={() => addPerson(n)}>{n}</button>)}
            </Fit>
            <div className="row">
              <button type="button" className="btn" onClick={() => setMeant(null)}>Change what I typed</button>
              <button type="button" className="btn" onClick={() => addPerson(typed.trim().replace(/\s+/g, " "))}>No, save “{typed.trim()}”</button>
            </div>
          </>
        ) : (
          <form className="contents" onSubmit={(e) => { e.preventDefault(); void typedName(); }}>
            <h2>Who else is in it?</h2>
            <label className="sr" htmlFor="who-add">Their full name</label>
            <input id="who-add" className="field" value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus list="who-names"
              placeholder="Their full name" autoCapitalize="words" autoComplete="off" enterKeyHint="done" />
            <datalist id="who-names">{names.map((n) => <option key={n} value={n} />)}</datalist>
            <div className="row">
              <button type="button" className="btn" onClick={() => { setTyped(""); setMode("who"); }}>Cancel</button>
              <button className="btn mint">Save this name</button>
            </div>
          </form>
        ))}

        {mode === "view" && (
          <>
            {p.video && <div className="caption"><p>{plays ? "A video" : "A still from a video"}</p></div>}
            <div className="facts">
              {fact("Who", who, "who", `Who: ${who}. Change who is in it`)}
              {fact("Where", where || "Not known yet", "where", `Where: ${where || "not known yet"}. Change the place`)}
              {fact("When", when || "Not known yet", "when", when ? `Taken ${when}. Change the year` : "Year not known. Add the year")}
            </div>
          </>
        )}
        {(mode === "view" || mode === "about") && (
          <div className={turns ? "turnrow turns" : "turnrow"}>
            {turns && turn(nav!.prev, "prev")}
            {turns && turn(nav!.next, "next")}
            <button className="btn grape about-btn" onClick={() => { setMode(about ? "view" : "about"); setSure(false); }}>
              <span>{about ? <>Show<span className="word"> the {noun}</span></> : <>About<span className="word"> this {noun}</span></>}</span>
            </button>
            <button className="btn sky send" onClick={share}><Share /> Send</button>
          </div>
        )}
        {last && mode === "view" && <Undo text={last.text} onUndo={undo} onDone={() => setLast(null)} />}
      </Squeeze>
    </div>
  );
}
