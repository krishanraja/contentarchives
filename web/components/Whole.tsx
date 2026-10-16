"use client";
import { useEffect, useState } from "react";

// The whole photograph, as big as the screen allows, without the ring or the
// dimming round it - and the other photos from that day, a tap each. Who is
// holding the baby is often in the next photo along (Krish, 2026-10-16).
export default function Whole({ src, day, onClose }: { src: string; day: string[]; onClose: () => void }) {
  const [shown, setShown] = useState(src);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    // the screen underneath is out of reach while this is open: no tap, no
    // screen reader, lands on the question behind the photo
    const behind = [...document.querySelectorAll<HTMLElement>(".bar, .page > :not(.whole-host)")];
    behind.forEach((el) => { el.inert = true; el.setAttribute("aria-hidden", "true"); });
    return () => {
      window.removeEventListener("keydown", key);
      behind.forEach((el) => { el.inert = false; el.removeAttribute("aria-hidden"); });
    };
  }, [onClose]);
  const pics = [{ thumb: src, big: src }, ...day.map((h) => ({ thumb: `/img/t/${encodeURIComponent(h)}`, big: `/img/v/${encodeURIComponent(h)}` }))];
  return (
    <div className="whole whole-host" role="dialog" aria-modal="true" aria-label="The whole photo">
      <div className="whole-top">
        <p>{day.length ? `This photo and ${day.length} more from that day` : "The whole photo"}</p>
        <button type="button" className="btn small sun" onClick={onClose} autoFocus>Back to the question</button>
      </div>
      <div className="whole-pic"><img src={shown} alt="The whole photo" /></div>
      {day.length > 0 && (
        <div className="strip" aria-label="Photos from the same day">
          {pics.slice(0, 5).map((p, i) => (
            <button key={p.big} type="button" aria-pressed={shown === p.big} onClick={() => setShown(p.big)}
              aria-label={i === 0 ? "This photo" : `Photo ${i + 1} from that day`}>
              <img src={p.thumb} alt="" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
