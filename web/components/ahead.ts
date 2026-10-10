"use client";
// The next question, asked for while this one is still being answered, and its
// pictures fetched into the browser's cache, so "Next" swaps it in at once
// instead of a blank "Finding…" and a picture that arrives seconds later.
// Held for one key only (what has been seen so far): any other next - after an
// undo, say - asks the server afresh, as it always did.

const MAX_AGE_MS = 120_000;   // older than this, someone else may have answered it

export function warm(src: string) {
  if (typeof window === "undefined") return;
  const i = new Image();
  i.src = src;
}

export function ahead<T>() {
  let held: { key: string; at: number; ready: boolean; p: Promise<T | undefined> } | null = null;
  return {
    start(key: string, get: () => Promise<T | undefined>, pictures: (v: NonNullable<T>) => string[]) {
      const h = { key, at: Date.now(), ready: false, p: get() };
      h.p.then((v) => { h.ready = true; if (v) pictures(v as NonNullable<T>).forEach(warm); });
      held = h;
    },
    // the held next if it is for exactly this key, and fresh; taken once
    take(key: string) {
      const h = held;
      held = null;
      return h && h.key === key && Date.now() - h.at < MAX_AGE_MS ? h : null;
    },
  };
}
