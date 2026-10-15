import { cookies, headers } from "next/headers";
import { inAppBrowser } from "@/lib/gate";
import { person, stepFor } from "@/lib/access";
import { ASKING, verifyAsking } from "@/lib/session";
import Ask from "@/components/Ask";
import GateHead from "@/components/GateHead";

export const dynamic = "force-dynamic";

// What /api/access answered, said plainly. A calm one is blue; a problem is red.
const SAID: Record<string, [string, "calm" | "red"]> = {
  email: ["That doesn't look like an email address. Check it and try again.", "red"],
  name: ["Type your first name first.", "red"],
  wrong: ["That's not the code. Check the email and try again.", "red"],
  old: ["That code has run out. Tap Send again for a new one.", "red"],
  spent: ["Too many wrong tries. Tap Send again for a new code.", "red"],
  locked: ["Too many tries. Please wait an hour, or ask Krish.", "red"],
  many: ["We've sent lots of codes. Please wait an hour, or ask Krish.", "red"],
  mail: ["We couldn't send the email just now. Please try again in a minute.", "red"],
  busy: ["Lots of people are asking right now. Please try again later, or ask Krish.", "red"],
  wait: ["We sent you a code a moment ago. Check your email.", "calm"],
  sent: ["We've emailed you a code. It can take a minute to arrive.", "calm"],
  reminded: ["We've asked Krish again.", "calm"],
};

const different = <Ask op="reset" label="Use a different email" busy="One moment…" tint="quiet" />;

// Signing in, one step at a time (Krish, 2026-10-15): your email; if you are
// new, your first name, so Krish can say yes; then the code we email you. The
// email typed is kept in a signed cookie, so coming back days later carries on.
export default async function Gate({ searchParams }: { searchParams: Promise<{ e?: string }> }) {
  const ua = (await headers()).get("user-agent") || "";
  const said = (await searchParams).e || "";
  const email = await verifyAsking((await cookies()).get(ASKING)?.value);
  const p = email ? await person(email) : null;
  const step = stepFor(email, p?.status || null);
  const [msg, tone] = SAID[said] || ["", "calm"];
  const note = <p id="gate-msg" role="alert" className={msg ? (tone === "red" ? "notice error" : "notice") : "sr"}>{msg}</p>;
  const addr = <span className="gate-addr">{email}</span>;
  return (
    <main className="page middle gate">
      {/* what is happening: on a phone on its side, beside what to do */}
      <div className="gate-side stack">
        <GateHead />
        {inAppBrowser(ua) && (
          <div className="notice" style={{ flex: "none" }}>
            <strong>Tip:</strong> tap the <strong>⋯</strong> menu and choose <strong>Open in Chrome</strong> or <strong>Open in Safari</strong>. Then it will remember you next time.
          </div>
        )}
        {step === "name" && <p className="gate-lead">New here? Krish lets each person in.</p>}
        {step === "code" && <p className="gate-lead">We emailed a code to {addr}</p>}
        {step === "waiting" && <p className="gate-lead">We'll email a code to {addr} when Krish says yes.</p>}
      </div>
      <div className="card" style={{ flex: "none" }} data-step={step}>
        {step === "email" && <>
          <Ask op="start" label="Send me a code" busy="Sending…" tint="tomato">
            <label className="big" htmlFor="email">Your email</label>
            <input id="email" name="email" type="email" className="field" required
              autoComplete="email" inputMode="email" autoCapitalize="none" autoCorrect="off" spellCheck={false}
              enterKeyHint="send" placeholder="you@example.com" aria-describedby="gate-msg" />
          </Ask>
          {note}
        </>}
        {step === "name" && <>
          <Ask op="ask" label="Ask Krish" busy="Asking…" tint="mint" pair>
            <label className="big" htmlFor="name">Your first name</label>
            <input id="name" name="name" className="field" required minLength={2} maxLength={40}
              autoComplete="given-name" autoCapitalize="words" enterKeyHint="send" placeholder="Your first name"
              aria-describedby="gate-msg" />
          </Ask>
          {note}
          {different}
        </>}
        {step === "waiting" && <>
          <p className="big">{said === "asked" ? `Thank you, ${p!.name}! Krish has been asked.` : "Krish hasn't said yes yet."}</p>
          {said !== "asked" && note}
          {different}
        </>}
        {step === "no" && <>
          <p className="big">Please speak to Krish about getting in.</p>
          {different}
        </>}
        {step === "code" && <>
          <Ask op="code" label="Open" busy="Opening…" tint="tomato" pair>
            <label className="big" htmlFor="code">Your code</label>
            <input id="code" name="code" className="field" required
              inputMode="numeric" autoComplete="one-time-code" autoCorrect="off" spellCheck={false}
              enterKeyHint="go" placeholder="6-digit code" aria-describedby="gate-msg" />
          </Ask>
          {note}
          <div className="row">
            <Ask op="resend" label="Send again" busy="Sending…" tint="quiet" />
            <Ask op="reset" label="Change email" busy="One moment…" tint="quiet" />
          </div>
        </>}
      </div>
    </main>
  );
}
