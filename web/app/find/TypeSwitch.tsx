import Go from "@/components/Go";
import type { Media } from "@/lib/search";

// All · Photos · Videos, on every Find screen (Krish, 2026-10-11: "filter by
// either at any point"). Three real links, so it works before the script
// arrives; the one in force is marked. Each says how many it would give.
export default function TypeSwitch({ active, counts, href }: {
  active: Media | null; counts: { photo: number; video: number }; href: (m: Media | null) => string;
}) {
  const n = (x: number) => x.toLocaleString("en-GB");
  // on the button, a short count: the live library's "Photos 18,726" did not
  // fit a phone's third of the row; the full number is read out
  const short = (x: number) => x < 1000 ? String(x) : x < 10000 ? `${(Math.floor(x / 100) / 10).toFixed(1).replace(/\.0$/, "")}k` : `${Math.floor(x / 1000)}k`;
  const opts: { m: Media | null; word: string; n: number }[] = [
    { m: null, word: "All", n: counts.photo + counts.video },
    { m: "photo", word: "Photos", n: counts.photo },
    { m: "video", word: "Videos", n: counts.video },
  ];
  return (
    <nav className="types" aria-label="Photos or videos">
      {opts.map((o) => (
        <Go key={o.word} className="btn small" href={href(o.m)} aria-current={active === o.m ? "page" : undefined}
          aria-label={`${o.word}, ${n(o.n)}`}>
          {o.m === "video" && <span className="play-dot" aria-hidden="true" />}
          {o.word}<span className="n" aria-hidden="true">{short(o.n)}</span>
        </Go>
      ))}
    </nav>
  );
}
