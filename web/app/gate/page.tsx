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
  old: ["That link or code has run out. Tap Send again for a new one.", "red"],
  spent: ["Too many wrong tries. Tap Send again for a new code.", "red"],
  locked: ["Too many tries. Please wait an hour, or ask Krish.", "red"],
  many: ["We've sent lots of codes. Please wait an hour, or ask Krish.", "red"],
  mail: ["We couldn't send the email just now. Please try again in a minute.", "red"],
  wait: ["We sent you an email a moment ago. Check your inbox.", "calm"],
  sent: ["We've emailed you a link. It can take a minute to arrive.", "calm"],
};

const different = <Ask op="reset" label="Use a different email" busy="One moment…" tint="quiet" />;

// Signing in, one step at a time (Krish, 2026-10-23: no approving each person):
// your email; if you are new, your first name; then tap the link we email you,
// or type its code here. The email typed is kept in a signed cookie, so coming
// back later carries on.
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
        {step === "name" && <p className="gate-lead">New here? Welcome! Tell us your first name.</p>}
        {step === "code" && <p className="gate-lead">We emailed a link to {addr}</p>}
      </div>
      <div className="card" style={{ flex: "none" }} data-step={step}>
        {step === "email" && <>
          <Ask op="start" label="Email me a link" busy="Sending…" tint="tomato">
            <label className="big" htmlFor="email">Your email</label>
            <input id="email" name="email" type="email" className="field" required
              autoComplete="email" inputMode="email" autoCapitalize="none" autoCorrect="off" spellCheck={false}
              enterKeyHint="send" placeholder="you@example.com" aria-describedby="gate-msg" />
          </Ask>
          {note}
        </>}
        {step === "name" && <>
          <Ask op="join" label="Email me a link" busy="Sending…" tint="mint" pair>
            <label className="big" htmlFor="name">Your first name</label>
            <input id="name" name="name" className="field" required minLength={2} maxLength={40}
              autoComplete="given-name" autoCapitalize="words" enterKeyHint="send" placeholder="Your first name"
              aria-describedby="gate-msg" />
          </Ask>
          {note}
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
