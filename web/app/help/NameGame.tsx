"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Shot from "@/components/Shot";
import Fit from "@/components/Fit";
import Undo from "@/components/Undo";
import Confetti from "@/components/Confetti";
import { send, uuid } from "@/components/outbox";
import { ahead } from "@/components/ahead";
import { close, exact, fold } from "@/lib/spelling";

type Face = { key: string; bbox: number[] };
type Sugg = { name: string; face: string; score: number };
type Q = { group: string; cluster: string; photos: number; hero: Face; samples: Face[]; suggestions: Sugg[]; ask: Sugg | null; contest: string[] } | null;

// "Nani" is a different person depending on who is speaking. Ask for a name.
const RELATION = new Set(["nani", "nana", "dadi", "dada", "mama", "mami", "masi", "mausi", "chacha",
  "chachi", "bua", "fufa", "aunty", "auntie", "aunt", "uncle", "mum", "mom", "mummy", "mother",
  "dad", "daddy", "papa", "father", "grandma", "grandpa", "granny", "grandad", "granddad", "nan",
  "bhaiya", "didi", "bhabhi", "jiju", "baby", "me", "myself", "cousin", "brother", "sister"]);

const faceUrl = (k: string, whole = false) => `/face/${encodeURIComponent(k)}${whole ? "?whole=1" : ""}`;
const getFace = (after: string[]): Promise<Q | undefined> =>
  fetch(`/api/face/next?after=${after.join(",")}`).then((x) => x.json()).catch(() => undefined);
// every picture the question will show
const pictures = (q: NonNullable<Q>) => [faceUrl(q.hero.key, true), ...q.samples.slice(0, 4).map((f) => faceUrl(f.key)),
  ...(q.ask ? [faceUrl(q.ask.face)] : []), ...q.suggestions.map((s) => faceUrl(s.face))];

export default function NameGame() {
  const [q, setQ] = useState<Q | undefined>(undefined);
  const [mode, setMode] = useState<"ask" | "choose" | "type" | "spell">("ask");
  const [meant, setMeant] = useState<string[]>([]);
  const [typed, setTyped] = useState("");
  const [names, setNames] = useState<string[]>([]);
  const [warn, setWarn] = useState("");
  const [done, setDone] = useState<{ name: string; n: number; id: string; group: string } | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [err, setErr] = useState("");
  const next = useRef(ahead<Q>());
  // an answer still on its way: undo waits for it, or it would arrive after the undo
  const sending = useRef(new Map<string, Promise<unknown>>());

  const load = useCallback(async (after: string[]) => {
    const held = next.current.take(after.join(","));
    if (!held?.ready) setQ(undefined);
    setErr("");
    let r = held ? await held.p : undefined;
    if (r === undefined) r = await getFace(after);
    if (r === undefined) { setErr("No internet connection. Your answers are safe on this phone."); setQ(null); return; }
    setQ(r); setMode(r?.ask ? "ask" : "choose"); setTyped(""); setWarn("");
    if (r) { const then = [...after, r.group]; next.current.start(then.join(","), () => getFace(then), pictures); }
  }, []);

  useEffect(() => { void load([]); fetch("/api/names").then((r) => r.json()).then((j) => setNames(j.people || [])).catch(() => undefined); }, [load]);

  const matches = useMemo(() => {
    const t = fold(typed);
    if (t.length < 1) return [];
    return names.filter((n) => fold(n).split(" ").some((w) => w.startsWith(t)) || fold(n).startsWith(t)).slice(0, 6);
  }, [typed, names]);

  // The screen moves on at the tap; the outbox keeps the answer until the
  // server has it. An answer the server refuses outright puts the face back,
  // with the reason, exactly as when the screen used to wait.
  async function answer(kind: "person" | "mixed", value: string) {
    if (!q) return;
    const asked = q, before = seen;
    const id = uuid();
    const p = send({ id, kind, group: asked.group, cluster: asked.cluster, value });
    sending.current.set(id, p);
    setSeen([...before, asked.group]);
    if (kind === "person") setDone({ name: value, n: asked.photos, id, group: asked.group });
    else void load([...before, asked.group]);
    const r = await p;
    sending.current.delete(id);
    if (!r.ok && r.error && !r.error.startsWith("offline")) {
      setDone(null); setSeen(before); setQ(asked); setMode(asked.ask ? "ask" : "choose"); setErr(r.error);
      return;
    }
    if (kind === "person" && r.labelled !== undefined) setDone((d) => (d && d.id === id ? { ...d, n: r.labelled! } : d));
  }

  // the skip is recorded while the next face is shown: it is left out by
  // `after` whether or not the skip has landed yet
  function dontKnow() {
    if (!q) return;
    void fetch("/api/skip", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: q.group }) }).catch(() => undefined);
    const after = [...seen, q.group];
    setSeen(after); setSkipped((n) => n + 1); void load(after);
  }

  function submitTyped() {
    const v = typed.trim().replace(/\s+/g, " ");
    if (v.length < 2) { setWarn("Please type their name."); return; }
    if (RELATION.has(v.toLowerCase())) {
      setWarn(`“${v}” means different people to different people. Please write their name, like “Asha Raja”.`);
      return;
    }
    // the same name however it is typed is that name; a near miss is ASKED
    // about, never merged: Asha and Isha may be two people
    const known = exact(v, names);
    if (known) { void answer("person", known); return; }
    const near = close(v, names);
    if (near.length) { setMeant(near); setMode("spell"); return; }
    void answer("person", v);
  }

  async function undo() {
    if (!done) return;
    await sending.current.get(done.id);
    await fetch("/api/answers/undo", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: done.id }) }).catch(() => undefined);
    const g = done.group;
    setDone(null); setSeen((s) => s.filter((x) => x !== g)); void load(seen.filter((x) => x !== g));
  }

  // Every state is one screen that never scrolls (Krish, 2026-10-05): the
  // photo takes the room the question leaves it, and a list of names longer
  // than its room turns like pages.
  if (done) {
    return (
      <div className="game middle">
        <Confetti seed={done.n} />
        <div className="yay stack" role="status">
          <p className="big">{done.n.toLocaleString("en-GB")}</p>
          <h2>{done.n === 1 ? "photo" : "photos"} now say <br />“{done.name}”</h2>
          <p>Thank you!</p>
        </div>
        <button className="btn block pink" onClick={() => { setDone(null); void load(seen); }}>Next face</button>
        <Link className="btn block" href="/">I'm done for now</Link>
        <Undo text={`Saved: ${done.name}`} onUndo={undo} onDone={() => undefined} />
      </div>
    );
  }
  if (q === undefined) return <p className="sentence" role="status">Finding a face…</p>;
  if (q === null) {
    return (
      <div className="game middle">
        {err ? <p className="notice error">{err}</p>
          : skipped > 0 ? <div className="yay"><h2>That's every face for now</h2><p>The ones you didn't know will come round again.</p></div>
          : <div className="yay"><h2>All done!</h2><p>There are no more faces to name right now. Thank you so much.</p></div>}
        {/* the faces they did not know, oldest "I don't know" first */}
        {!err && skipped > 0 && <button className="btn block pink" onClick={() => { setSeen([]); setSkipped(0); void load([]); }}>Look at those again</button>}
        <Link className="btn block sun" href="/">Back home</Link>
      </div>
    );
  }

  const others = q.suggestions.filter((s) => !q.contest.some((n) => fold(n) === fold(s.name)));
  const typedNow = typed.trim().replace(/\s+/g, " ");
  return (
    <div className={`game ${mode}`}>
      <Shot src={faceUrl(q.hero.key, true)} bbox={q.hero.bbox} alt="A photo with one face circled" />
      {q.samples.length > 0 && mode !== "type" && (
        <div className="samples">
          <p className="muted">The same person?</p>
          {q.samples.slice(0, 4).map((f) => <img key={f.key} src={faceUrl(f.key)} alt="" />)}
        </div>
      )}
      {/* right under the faces it is about */}
      {(mode === "ask" || mode === "choose") && q.samples.length > 0 && (
        <button className="btn block quiet notsame" onClick={() => answer("mixed", "mixed")}>These aren't all the same person</button>
      )}
      <div className="panel">
        {err && <p className="notice error" role="alert">{err}</p>}

        {mode === "ask" && q.ask && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <img src={faceUrl(q.ask.face)} alt="" style={{ width: "clamp(52px, 8cqh, 76px)", aspectRatio: "1", borderRadius: "50%", border: "3px solid var(--ink)", flex: "none" }} />
              <h2>Is this {q.ask.name}?</h2>
            </div>
            <div className="row">
              <button className="btn" onClick={() => setMode("choose")}>No</button>
              <button className="btn mint" onClick={() => answer("person", q.ask!.name)}>Yes!</button>
            </div>
            <button className="btn block" onClick={dontKnow}>I don't know</button>
          </>
        )}

        {mode === "choose" && (
          <>
            {q.contest.length > 0
              ? <h2>People said different names. Which is right?</h2>
              : <h2 className="said-above">Who is this?</h2>}
            {(q.contest.length > 0 || others.length > 0) && (
              <Fit label={q.contest.length ? "Names people have given" : "Names it might be"} more="More names">
                {[
                  ...q.contest.map((n) => {
                    const f = q.suggestions.find((s) => fold(s.name) === fold(n));
                    return (
                      <button key={"c:" + n} className="chip" onClick={() => answer("person", n)}>
                        {f && <img src={faceUrl(f.face)} alt="" />}{n}
                      </button>
                    );
                  }),
                  ...others.map((s) => (
                    <button key={"s:" + s.name} className="chip" onClick={() => answer("person", s.name)}>
                      <img src={faceUrl(s.face)} alt="" />{s.name}
                    </button>
                  )),
                ]}
              </Fit>
            )}
            <div className="row">
              <button className="btn sky" onClick={() => setMode("type")}>{q.suggestions.length || q.contest.length ? "Someone else" : "Type their name"}</button>
              <button className="btn" onClick={dontKnow}>I don't know</button>
            </div>
          </>
        )}

        {mode === "type" && (
          <form className="contents" onSubmit={(e) => { e.preventDefault(); submitTyped(); }}>
            <label className="big" htmlFor="nm">Their name</label>
            <input id="nm" className="field" value={typed} onChange={(e) => { setTyped(e.target.value); setWarn(""); }}
              autoComplete="off" autoCapitalize="words" autoCorrect="off" spellCheck={false} enterKeyHint="done" placeholder="First and last name" />
            {matches.length > 0 && (
              <Fit key={typed} label="Names we already know" more="More names">
                {matches.map((n) => <button type="button" key={n} className="chip" onClick={() => answer("person", n)}>{n}</button>)}
              </Fit>
            )}
            {warn && <p className="notice error" role="alert">{warn}</p>}
            <div className="row">
              <button type="button" className="btn" onClick={() => setMode(q.ask ? "ask" : "choose")}>Go back</button>
              <button className="btn pink">Save this name</button>
            </div>
          </form>
        )}

        {mode === "spell" && (
          <>
            <h2>Did you mean {meant.length === 1 ? `${meant[0]}?` : "one of these?"}</h2>
            <Fit label="Names we already know" more="More names">
              {meant.map((n) => <button key={n} className="chip" onClick={() => answer("person", n)}>{n}</button>)}
            </Fit>
            <div className="row">
              <button className="btn" onClick={() => setMode("type")}>Change what I typed</button>
              <button className="btn" onClick={() => answer("person", typedNow)}>No, save “{typedNow}”</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
