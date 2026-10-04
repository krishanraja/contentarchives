import Link from "next/link";
import { Home } from "./icons";

// One obvious way home, on every screen but home itself.
export default function Bar({ title }: { title: string }) {
  return (
    <header className="bar">
      <div className="bar-inner">
        <Link href="/" className="btn small sun" aria-label="Go to the home screen"><Home /> Home</Link>
        <span className="title">{title}</span>
      </div>
    </header>
  );
}
