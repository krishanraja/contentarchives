// How the family's answer about when reads: "1987", or "The 1980s". Plain code,
// used on the server (the photo page) and on the phone (after an answer).
export const whenLabel = (v: string) => (/s$/.test(v) ? `The ${v}` : v);
