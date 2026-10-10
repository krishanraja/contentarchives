// One value, loaded once and kept for a while by this server instance. Callers
// that arrive while it is loading share the same load; a failed load is never
// kept, so the next caller tries again.
export function memo<T>(load: () => Promise<T>, ttlMs: number, now: () => number = Date.now) {
  let hit: { at: number; value: Promise<T> } | null = null;
  return {
    async get(): Promise<T> {
      if (!hit || now() - hit.at >= ttlMs) {
        const value = load();
        const mine = { at: now(), value };
        hit = mine;
        value.catch(() => { if (hit === mine) hit = null; });
      }
      return hit.value;
    },
    clear() { hit = null; },
  };
}
