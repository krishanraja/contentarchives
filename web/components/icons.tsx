// Hand-drawn-feeling icons, thick strokes so they read at arm's length.
const s = { fill: "none", stroke: "currentColor", strokeWidth: 2.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
export const Search = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5 21 21" /></svg>);
export const Face = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><circle cx="12" cy="12" r="9" /><path d="M8.5 14.5c1 1.4 2.2 2 3.5 2s2.5-.6 3.5-2" /><path d="M9 9.5h.01M15 9.5h.01" strokeWidth={3.4} /></svg>);
export const Pin = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><path d="M12 21s-6.5-6.1-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.9 12 21 12 21Z" /><circle cx="12" cy="9.8" r="2.4" /></svg>);
export const Home = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><path d="M3.5 11 12 4l8.5 7" /><path d="M6 9.5V20h12V9.5" /></svg>);
export const Back = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><path d="M15 5 8 12l7 7" /></svg>);
export const Share = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><path d="M12 15V3.5M7.5 8 12 3.5 16.5 8" /><path d="M5 12.5V20h14v-7.5" /></svg>);
export const Eye = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><path d="M3 3l18 18" /><path d="M10.6 6.1A9.9 9.9 0 0 1 12 6c5 0 8.5 4.5 9.5 6-.5.8-1.6 2.2-3.1 3.5M6.6 7.6C4.6 9 3.2 11 2.5 12c1 1.5 4.5 6 9.5 6 1.6 0 3-.5 4.3-1.1" /></svg>);
export const Mic = () => (<svg viewBox="0 0 24 24" aria-hidden="true" {...s}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></svg>);
