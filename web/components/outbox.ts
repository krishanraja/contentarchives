"use client";
// Answers wait on the phone until the server says it has them. A lift, a
// tunnel or a tired battery cannot lose one: each has its own id from the
// moment it is tapped, so sending it twice is the same answer, never two.

const KEY = "archives.outbox.v1";
export type Pending = { id: string; body: Record<string, unknown>; tries: number };

function read(): Pending[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}
function write(list: Pending[]) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* private mode: still sent live */ }
}

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (Number(c) ^ (Math.random() * 16) >> (Number(c) / 4)).toString(16));
}

export function pending(): number { return read().length; }

// Send one answer now; if the network fails, keep it and try again later.
export async function send(body: Record<string, unknown>): Promise<{ ok: boolean; labelled?: number; error?: string }> {
  const id = String(body.id);
  write([...read().filter((p) => p.id !== id), { id, body, tries: 0 }]);
  return flushOne(id);
}

async function flushOne(id: string) {
  const item = read().find((p) => p.id === id);
  if (!item) return { ok: true };
  try {
    const r = await fetch("/api/answers", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...item.body, client_at: item.body.client_at || new Date().toISOString() }),
    });
    const j = await r.json().catch(() => ({}));
    // 2xx: saved. 400/422: can never succeed - drop it rather than retry forever.
    if (r.ok || r.status === 400 || r.status === 422) write(read().filter((p) => p.id !== id));
    return r.ok ? { ok: true, labelled: j.labelled } : { ok: false, error: j.error || "not saved" };
  } catch {
    write(read().map((p) => (p.id === id ? { ...p, tries: p.tries + 1 } : p)));
    return { ok: false, error: "offline - it will be sent when you are back online" };
  }
}

export async function flushAll() {
  for (const p of read()) await flushOne(p.id);
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => { void flushAll(); });
  setTimeout(() => { void flushAll(); }, 1500);
}
