import type { Metadata, Viewport } from "next";
import { Atkinson_Hyperlegible, Fredoka } from "next/font/google";
import "./globals.css";

// Atkinson Hyperlegible was designed by the Braille Institute for readers
// with low vision: every letter that could be mistaken for another is not.
const body = Atkinson_Hyperlegible({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-body" });
const display = Fredoka({ subsets: ["latin"], weight: ["600"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "Family Archives",
  description: "Our family's photographs.",
  robots: { index: false, follow: false },
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#fff6e9",
};

// A PHONE THAT ASKS FOR THE DESKTOP PAGE STILL GETS THE PHONE PAGE. Krish's
// phone (412 px wide) laid this out 1,040 px wide - Chrome's "Desktop site", or
// its zoom turned down - so everything sat in a narrow column at less than half
// size. A browser doing that ignores the viewport tag, so before the first paint
// this scales the page back up to the phone's own width: a touch screen no wider
// than 600 px whose page is laid out much wider. Phones, tablets and computers
// that lay out at their own width are untouched; it re-checks on rotation.
const FIT_PHONE = `(function(){function f(){try{var d=document.documentElement,s=screen.width,w=window.innerWidth;
if(navigator.maxTouchPoints>0&&s>0&&s<=600&&w>s*1.3){d.style.zoom=String(w/s)}else if(d.style.zoom){d.style.zoom=""}}catch(e){}}
f();addEventListener("resize",f);addEventListener("orientationchange",f)})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" className={`${body.variable} ${display.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: FIT_PHONE }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
