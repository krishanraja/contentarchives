import Link from "next/link";
import { Back, Home } from "./icons";

// One obvious way home, on every screen but home itself - always top left.
// A screen reached from a list also offers the way back to that list, in the
// title's place (Krish, 2026-10-06: back to the photos without hunting for it).
export default function Bar({ title, back }: { title: string; back?: { href: string; label: string } }) {
  return (
    <header className="bar">
      <div className="bar-inner">
        <Link href="/" className="btn small sun" aria-label="Go to the home screen"><Home /> Home</Link>
        {back
          ? <Link href={back.href} className="btn small"><Back /> {back.label}</Link>
          : <span className="title">{title}</span>}
      </div>
    </header>
  );
}
