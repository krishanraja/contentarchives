import { headers } from "next/headers";
import { inAppBrowser } from "@/lib/gate";
import GateForm from "./GateForm";

export default async function Gate({ searchParams }: { searchParams: Promise<{ e?: string }> }) {
  const ua = (await headers()).get("user-agent") || "";
  const said = (await searchParams).e || "";
  return (
    <main className="page middle gate">
      <div className="center stack" style={{ gap: 6, flex: "none" }}>
        <div className="art" aria-hidden="true" style={{ fontSize: 0 }}>
          <svg viewBox="0 0 120 90" width="150" height="112" style={{ height: "clamp(64px, 14cqh, 112px)", width: "auto" }}>
            <rect x="8" y="14" width="74" height="60" rx="10" fill="#ff9ccf" stroke="#1e1433" strokeWidth="4" transform="rotate(-8 45 44)" />
            <rect x="36" y="10" width="74" height="60" rx="10" fill="#ffc93c" stroke="#1e1433" strokeWidth="4" transform="rotate(7 73 40)" />
            <circle cx="66" cy="34" r="8" fill="#fff" stroke="#1e1433" strokeWidth="4" />
            <path d="M44 62l16-16 12 10 10-8 18 16" fill="none" stroke="#1e1433" strokeWidth="4" strokeLinejoin="round" />
          </svg>
        </div>
        <h1>Family Archives</h1>
        <p className="muted sub">All our photos, in one place.</p>
      </div>
      {inAppBrowser(ua) && (
        <div className="notice" style={{ flex: "none" }}>
          <strong>Tip:</strong> tap the <strong>⋯</strong> menu and choose <strong>Open in Chrome</strong> or <strong>Open in Safari</strong>. Then it will remember you next time.
        </div>
      )}
      <GateForm said={said} />
    </main>
  );
}
