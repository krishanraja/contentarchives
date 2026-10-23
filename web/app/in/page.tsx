import type { Metadata } from "next";
import { verifyLink } from "@/lib/session";
import Ask from "@/components/Ask";
import GateHead from "@/components/GateHead";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false } };

// Where the link in a sign-in email leads. Opening it only shows a button:
// mail scanners open every link in an email, and a link that signed in on
// opening would spend the code on the scanner. The tap, posted to
// /api/access, is what signs this phone in.
export default async function In({ searchParams }: { searchParams: Promise<{ t?: string }> }) {
  const { t = "" } = await searchParams;
  const ok = !!(await verifyLink(t));
  return (
    <main className="page middle gate">
      <div className="gate-side stack"><GateHead /></div>
      <div className="card" style={{ flex: "none" }} data-link={ok ? "ok" : "bad"}>
        {ok
          ? <Ask op="link" hidden={{ t }} label="Open the Family Archives" busy="Opening…" tint="tomato" />
          : <>
            <p className="big">This link has run out, or isn't quite right.</p>
            <a className="btn block quiet" href="/gate">Get a new one</a>
          </>}
      </div>
    </main>
  );
}
