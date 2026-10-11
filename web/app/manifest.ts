import type { MetadataRoute } from "next";

// What a phone shows when the app is added to its home screen: the app's own
// icon (scripts/make-icons.ts). It still opens in the browser: a home-screen
// app on an iPhone keeps its own cookies, and a grandparent would be asked for
// the family code a second time.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Family Archives",
    short_name: "Archives",
    start_url: "/",
    display: "browser",
    background_color: "#fff6e9",
    theme_color: "#fff6e9",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
