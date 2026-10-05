"use client";
import { Children, cloneElement, isValidElement, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

// A list that never makes its screen scroll (Krish, 2026-10-05). It shows as
// many of its items as fit in the room the screen gives it, and turns to the
// rest like the pages of a book: "More ›" is the last item on the page and
// "‹ Back" the first, so turning costs no extra row. An item that does not
// fit is not shown at all (never half a button). When everything fits, the
// list takes only the room it needs and the photo on the same screen gets the
// rest.
//
// `cells`: a grid of photos whose rows are sized to fill the room exactly,
// so no strip of empty screen is left under the last row; it turns with a
// row of two buttons under the grid.
// `total`/`need`: a list still arriving (search results); `need(n)` asks for
// at least n items.
const useIso = typeof window === "undefined" ? useEffect : useLayoutEffect;
const CAP = 80;
const SHADOW = 5;          // the chips' and photos' drop shadow, kept inside the room

type Fitted = { shown: number; natural: number; floor: number; rowH?: number };
const same = (a: Fitted | null, b: Fitted) =>
  !!a && a.shown === b.shown && Math.abs(a.natural - b.natural) < 1 && Math.abs(a.floor - b.floor) < 1 && a.rowH === b.rowH;

export default function Fit({ children, className = "chips", label, more = "More", total, need, cells = false, turn = "chip turn" }: {
  children: ReactNode; className?: string; label?: string; more?: string;
  total?: number; need?: (n: number) => void; cells?: boolean; turn?: string;
}) {
  const all = Children.toArray(children);
  const count = Math.max(total ?? 0, all.length);
  const [starts, setStarts] = useState<number[]>([0]);
  const start = Math.min(starts[starts.length - 1], Math.max(0, all.length - 1));
  const [f, setF] = useState<Fitted | null>(null);   // null: not measured yet (before the script)
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const pager = useRef<HTMLDivElement>(null);
  const items = all.slice(start, start + CAP);
  const left = count - start;

  useIso(() => {
    const b = box.current, l = list.current;
    if (!b || !l) return;
    const put = (v: Fitted) => setF((old) => (same(old, v) ? old : v));
    const measure = () => {
      const room = b.clientHeight - SHADOW;
      const gap = parseFloat(getComputedStyle(l).rowGap) || 0;
      if (cells) {
        // as many whole rows as fit; the rows share the room exactly
        const pagerH = pager.current ? pager.current.offsetHeight + gap : 0;
        const cols = Math.max(1, getComputedStyle(l).gridTemplateColumns.split(" ").length);
        const cellW = (l.clientWidth - SHADOW - (cols - 1) * gap) / cols;
        let rows = Math.max(1, Math.round((room + gap) / (cellW + gap)));
        while (rows > 1 && (room - (rows - 1) * gap) / rows < cellW * 0.6) rows--;
        const rowH = Math.max(56, Math.min((room - (rows - 1) * gap) / rows, cellW * 1.35));
        const used = Math.ceil(Math.min(left, rows * cols) / cols);
        put({ shown: rows * cols, rowH, natural: used * rowH + (used - 1) * gap + SHADOW, floor: 56 + SHADOW + pagerH });
        return;
      }
      // Try n items (and "More ›" after them when any are left) straight on the
      // page, read where the last one lands, and put the page back as it was.
      const kids = Array.from(l.children) as HTMLElement[];
      const moreK = kids.find((k) => k.dataset.turn === "more");
      const backK = kids.find((k) => k.dataset.turn === "back");
      const its = kids.filter((k) => !k.dataset.turn);
      const saved = kids.map((k) => k.style.display);
      const bottom = (n: number) => {
        its.forEach((k, i) => { k.style.display = i < n ? "" : "none"; });
        const more = n < left;
        if (moreK) moreK.style.display = more ? "" : "none";
        const last = more ? moreK : its[n - 1] || backK;
        return last ? last.offsetTop + last.offsetHeight : 0;
      };
      let n = its.length;
      const whole = bottom(its.length);
      const natural = l.offsetHeight;
      if (!(its.length >= left && whole <= room + 0.5)) {
        let lo = 1, hi = its.length;              // the most that fit with "More ›" after them
        n = 1;
        while (lo <= hi) {
          const mid = (lo + hi) >> 1;
          if (bottom(mid) <= room + 0.5) { n = mid; lo = mid + 1; } else hi = mid - 1;
        }
      }
      const floor = bottom(1) + SHADOW;
      kids.forEach((k, i) => { k.style.display = saved[i]; });
      put({ shown: Math.max(1, n), natural, floor });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(b); ro.observe(l);
    if (pager.current) ro.observe(pager.current);
    // the family's fonts arrive after the first measure, and are wider
    let live = true;
    document.fonts?.ready.then(() => { if (live) measure(); });
    return () => { live = false; ro.disconnect(); };
  }, [start, all.length, cells, count]);

  const shown = f?.shown ?? null;
  const fitsAll = shown !== null && start === 0 && shown >= count;
  const paging = shown !== null && !fitsAll;
  useEffect(() => {
    if (need && shown !== null && start + shown * 2 > all.length && all.length < count) need(start + shown * 2);
  }, [need, shown, start, all.length, count]);

  const back = () => setStarts((s) => (s.length > 1 ? s.slice(0, -1) : s));
  const next = () => setStarts((s) => [...s, start + (shown ?? 1)]);
  const style: React.CSSProperties = {};
  if (f) style.minHeight = f.floor;
  if (fitsAll && f) { style.maxHeight = f.natural; style.minHeight = Math.min(f.floor, f.natural); }
  return (
    <div className="fit" style={style}>
      <div className="fit-box" ref={box}>
        <div className={cells && f?.rowH ? `${className} sized` : className} ref={list} aria-label={label}
          style={cells && f?.rowH ? { gridAutoRows: `${f.rowH}px` } : undefined}>
          {!cells && start > 0 && (
            <button type="button" key="__back" data-turn="back" className={turn} onClick={back}>‹ Back</button>
          )}
          {/* each item is one element; one that does not fit is not shown */}
          {items.map((c, i) => (shown !== null && i >= shown && isValidElement<{ style?: object }>(c)
            ? cloneElement(c, { style: { ...c.props.style, display: "none" }, "aria-hidden": true } as object)
            : c))}
          {!cells && (
            <button type="button" key="__more" data-turn="more" className={turn} aria-label={more} onClick={next}
              style={shown !== null && start + shown < count ? undefined : { display: "none" }}>More ›</button>
          )}
        </div>
      </div>
      {cells && paging && (
        <div className="fit-pager" ref={pager}>
          {start > 0 && <button type="button" className="btn small" aria-label="Back to the ones before" onClick={back}>‹ Back</button>}
          {start + (shown ?? 0) < count && <button type="button" className="btn small" aria-label={more} onClick={next}>More ›</button>}
        </div>
      )}
    </div>
  );
}
