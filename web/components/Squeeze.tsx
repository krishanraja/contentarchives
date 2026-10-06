"use client";
import { useEffect, useLayoutEffect, useRef, type ReactNode } from "react";

// Boxes that give up detail, one step at a time, until their screen fits -
// measured on the phone itself, never guessed from its screen size.
// Krish's phone, 2026-10-06: a phone's browser reports one height to the
// stylesheet (as if the address bar were hidden) and gives the page another,
// so a rule like "hide the sentence below 800px" never fired and the home
// tiles' words spilled over each other. Here the page itself is measured:
// level 0 shows everything; each higher level (data-fit, globals.css) shows
// less; the lowest level at which nothing spills off the page wins. A box
// never shrinks below its own words - if even the last level does not fit,
// the page scrolls rather than lay words over words.
const useIso = typeof window === "undefined" ? useEffect : useLayoutEffect;

export default function Squeeze({ className, levels, children }: { className: string; levels: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useIso(() => {
    const el = ref.current;
    const page = el?.closest(".page") as HTMLElement | null;
    if (!el || !page) return;
    const fit = () => {
      for (let lv = 0; lv <= levels; lv++) {
        el.dataset.fit = String(lv);
        if (page.scrollHeight <= page.clientHeight + 1) return;
      }
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(page);
    let live = true;
    document.fonts?.ready.then(() => { if (live) fit(); });
    return () => { live = false; ro.disconnect(); };
  }, [levels]);
  return <div ref={ref} className={className}>{children}</div>;
}
