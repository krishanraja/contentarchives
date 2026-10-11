import Link from "next/link";
import type { Media } from "@/lib/search";

// All · Photos · Videos, on every Find screen (Krish, 2026-10-11: "filter by
// either at any point"). Three real links, so it works before the script
// arrives; the one in force is marked. Each says how many it would give.
export default function TypeSwitch({ active, counts, href }: {
  active: Media | null; counts: { photo: number; video: number }; href: (m: Media | null) => string;
}) {
  const n = (x: number) => x.toLocaleString("en-GB");
  const opts: { m: Media | null; word: string; n: number }[] = [
    { m: null, word: "All", n: counts.photo + counts.video },
    { m: "photo", word: "Photos", n: counts.photo },
    { m: "video", word: "Videos", n: counts.video },
  ];
  return (
    <nav className="types" aria-label="Photos or videos">
      {opts.map((o) => (
        <Link key={o.word} className="btn small" href={href(o.m)} aria-current={active === o.m ? "page" : undefined}
          aria-label={`${o.word}, ${n(o.n)}`}>
          {o.m === "video" && <span className="play-dot" aria-hidden="true" />}
          {o.word}<span className="n" aria-hidden="true">{n(o.n)}</span>
        </Link>
      ))}
    </nav>
  );
}
