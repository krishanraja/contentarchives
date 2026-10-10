// Names and places are typed by people on phones, often by older people with
// large thumbs. Two rules (Krish, 2026-10-05: "if someone misspells, it handles
// that too"):
//
//  1. Differences that are not spelling - case, spacing, punctuation, Unicode
//     form - are not differences. fold() is the same key the database uses
//     (name_key in migration 0007), so "asha raja" and "Asha  Raja." are one
//     answer for one person everywhere.
//  2. A REAL difference in spelling is never merged silently: Asha and Isha
//     may be two people. close() finds the known names a typed one is probably
//     meant to be, and the person is asked "Did you mean ...?" - one tap to
//     take it, one tap to keep what they typed.

export function fold(s: string): string {
  return (s || "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

// Damerau-Levenshtein (optimal string alignment): a swapped pair of letters is
// one slip, as it is on a phone keyboard.
export function distance(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (!m) return n;
  if (!n) return m;
  const d: number[][] = Array.from({ length: m + 1 }, (_, i) => [i, ...new Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[m][n];
}

// how many slips a word of this length may carry and still be "probably meant"
const slack = (len: number) => (len <= 3 ? 0 : len <= 5 ? 1 : len <= 9 ? 2 : 3);

// the known entry this one folds to exactly, if any
export function exact(typed: string, known: string[]): string | null {
  const k = fold(typed);
  return known.find((n) => fold(n) === k) || null;
}

// The spelling a saved answer takes: a known one it folds to, else one given
// since the known list was read (another phone, a minute ago), else as typed.
// `recent` is asked only when the list has no match, so a save that picked a
// known name never touches the database for it.
export async function spellAs(typed: string, known: string[], recent: () => Promise<string[]>): Promise<string> {
  return exact(typed, known) || exact(typed, await recent()) || typed;
}

// The known names a typed one is probably meant to be, closest first (at most
// `max`). Whole names are compared, and so is each word, so "Ashwin" finds
// "Ashvin Raja" and "Usha Rja" finds "Usha Raja".
export function close(typed: string, known: string[], max = 3): string[] {
  const t = fold(typed);
  if (!t || exact(typed, known)) return [];
  const tw = t.split(" ");
  const scored: { name: string; score: number }[] = [];
  for (const name of known) {
    const k = fold(name);
    if (!k) continue;
    let best = distance(t, k) <= slack(Math.max(t.length, k.length)) ? distance(t, k) : Infinity;
    const kw = k.split(" ");
    if (best === Infinity) {
      // every typed word close to a different word of the known name
      const used = new Set<number>();
      let total = 0, ok = tw.length > 0;
      for (const w of tw) {
        let hit = -1, hd = Infinity;
        kw.forEach((x, i) => {
          if (used.has(i)) return;
          const dd = distance(w, x);
          if (dd <= slack(Math.max(w.length, x.length)) && dd < hd) { hd = dd; hit = i; }
        });
        if (hit < 0) { ok = false; break; }
        used.add(hit);
        total += hd;
      }
      if (ok) best = total + 0.5;               // a word-by-word match ranks after a whole-name one
    }
    if (best !== Infinity && best > 0) scored.push({ name, score: best });
  }
  return scored.sort((a, b) => a.score - b.score || a.name.localeCompare(b.name)).slice(0, max).map((s) => s.name);
}
