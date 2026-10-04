"use client";
// The whole photograph with a ring around the face being asked about - a
// person is recognisable from their clothes and the room long before a tiny
// face is (people_sheet.context(), 2026-09-18). bbox is fractions, so the ring
// lands in the same place at any size the picture is drawn.
export default function Ringed({ src, bbox, alt }: { src: string; bbox?: number[]; alt: string }) {
  let ring = null;
  if (bbox && bbox.length === 4) {
    const [x1, y1, x2, y2] = bbox;
    const w = x2 - x1, h = y2 - y1, pad = 0.45;
    const side = Math.max(w, h);
    ring = (
      <span className="ring" style={{
        left: `${((x1 + x2) / 2 - (w * (1 + pad)) / 2) * 100}%`,
        top: `${((y1 + y2) / 2 - (h * (1 + pad)) / 2) * 100}%`,
        width: `${w * (1 + pad) * 100}%`,
        height: `${h * (1 + pad) * 100}%`,
        minWidth: 44, minHeight: 44,
        borderRadius: side > 0 ? "50%" : undefined,
      }} />
    );
  }
  return (
    <div className="hero" style={{ display: "grid", placeItems: "center" }}>
      <span style={{ position: "relative", display: "inline-block", lineHeight: 0, maxWidth: "100%" }}>
        <img src={src} alt={alt} style={{ width: "auto", maxWidth: "100%" }} />
        {ring}
      </span>
    </div>
  );
}
