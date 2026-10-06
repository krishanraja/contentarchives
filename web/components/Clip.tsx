"use client";
import { useEffect, useRef, useState } from "react";

// A family video, played where its photograph would be: at its own shape, as
// big as the room the screen leaves it and never bigger, so nothing scrolls
// (Krish, 2026-10-05). The phone's own controls - one big play button - and
// its still as the picture until it plays. Nothing plays by itself. If the
// phone cannot play it after all, `onFail` puts the still back.
export default function Clip({ hash, alt, onFail }: { hash: string; alt: string; onFail: () => void }) {
  const [ar, setAr] = useState(16 / 9);
  const v = useRef<HTMLVideoElement>(null);
  const h = encodeURIComponent(hash);
  const took = (el: HTMLVideoElement | null) => {
    if (el && el.videoWidth && el.videoHeight) setAr(el.videoWidth / el.videoHeight);
  };
  // the page's own player starts reading before the script arrives: a video
  // that already failed, or already knows its shape, said so before anyone listened
  useEffect(() => {
    if (v.current?.error) onFail();
    else took(v.current);
  }, [onFail]);
  return (
    <div className="slot">
      <div className="frame clip" style={{ ["--ar" as string]: ar }}>
        <video ref={v} controls playsInline preload="metadata" poster={`/img/v/${h}`} src={`/video/${h}`}
          aria-label={alt} onLoadedMetadata={(e) => took(e.currentTarget)} onError={onFail} />
      </div>
    </div>
  );
}
