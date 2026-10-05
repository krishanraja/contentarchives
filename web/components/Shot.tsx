"use client";
import { useEffect, useRef, useState } from "react";

// A photograph that takes the room its screen leaves it, at its own shape,
// and never more: the app does not scroll (Krish, 2026-10-05). With `bbox`
// (fractions of the picture) a ring is drawn round the face being asked about
// - a person is recognisable from their clothes and the room long before a
// tiny face is (people_sheet.context(), 2026-09-18) - in the same place at any
// size the picture is drawn.
export default function Shot({ src, alt, bbox }: { src: string; alt: string; bbox?: number[] }) {
  const [ar, setAr] = useState(4 / 3);
  const img = useRef<HTMLImageElement>(null);
  const took = (i: HTMLImageElement | null) => {
    if (i && i.naturalWidth && i.naturalHeight) setAr(i.naturalWidth / i.naturalHeight);
  };
  // a picture already in the cache can finish loading before the script arrives
  useEffect(() => { if (img.current?.complete) took(img.current); }, [src]);

  let ring = null;
  if (bbox && bbox.length === 4) {
    const [x1, y1, x2, y2] = bbox;
    const w = x2 - x1, h = y2 - y1, pad = 0.45;
    ring = (
      <span className="ring" style={{
        left: `${((x1 + x2) / 2 - (w * (1 + pad)) / 2) * 100}%`,
        top: `${((y1 + y2) / 2 - (h * (1 + pad)) / 2) * 100}%`,
        width: `${w * (1 + pad) * 100}%`,
        height: `${h * (1 + pad) * 100}%`,
        minWidth: 44, minHeight: 44,
      }} />
    );
  }
  return (
    <div className="slot">
      <div className="frame" style={{ ["--ar" as string]: ar }}>
        <img ref={img} src={src} alt={alt} onLoad={(e) => took(e.currentTarget)} />
        {ring}
      </div>
    </div>
  );
}
