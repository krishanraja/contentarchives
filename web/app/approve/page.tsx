import type { Metadata } from "next";
import { person } from "@/lib/access";
import { verifyDecide } from "@/lib/session";
import Ask from "@/components/Ask";
import GateHead from "@/components/GateHead";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false } };

// Where Krish's "someone would like to come in" email leads. Opening it only
// shows the question: mail scanners open every link in an email, so a link
// that decided on opening would let everyone in. A tap on a button,
// posted to /api/access, is the decision.
export default async function Approve({ searchParams }: { searchParams: Promise<{ t?: string; e?: string }> }) {
  const { t = "", e = "" } = await searchParams;
  const email = await verifyDecide(t);
  const p = email ? await person(email) : null;
  const yes = (label: string) => <Ask op="decide" hidden={{ t, d: "yes" }} label={label} busy="Saving…" tint="mint" />;
  return (
    <main className="page middle gate">
      <div className="gate-side stack"><GateHead /></div>
      <div className="card" style={{ flex: "none" }} data-status={p?.status || "bad"}>
        {!p && <p className="big">This link has run out, or isn't quite right.</p>}
        {p?.status === "asked" && <>
          <h2>{p.name} would like to come in</h2>
          <p className="muted">Their email: <span className="gate-addr">{p.email}</span></p>
          <div className="gate-choice">
            {yes(`Yes, let ${p.name} in`)}
            <Ask op="decide" hidden={{ t, d: "no" }} label="No" busy="Saving…" tint="quiet" />
          </div>
        </>}
        {p?.status === "yes" && <>
          <h2>{p.name} can come in</h2>
          <p role="status" className={e === "mail" ? "notice error" : ""}>{e === "mail"
            ? "The email with their code didn't go. They can type their email on the sign-in page to get one."
            : "They have been emailed a code."}</p>
        </>}
        {p?.status === "no" && <>
          <h2>You said no to {p.name}</h2>
          {yes(`Let ${p.name} in after all`)}
        </>}
      </div>
    </main>
  );
}
