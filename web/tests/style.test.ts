import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Krish's phone, 2026-10-06: a phone's browser answers "@media (max-height)"
// with the height it would have with the address bar hidden, not the height
// the page really gets, so a size rule written that way can fail to fire and
// let words spill over each other. Every size rule must ask the screen the
// page really has (@container screen, globals.css); only a person's own
// settings (reduced motion and the like) may be asked of the window.
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

describe("the stylesheet sizes things by the screen the page really has", () => {
  it("no @media rule asks the window's height, width, orientation or shape", () => {
    const media = css.match(/@media[^{]*/g) || [];
    expect(media.filter((m) => /height|width|orientation|aspect-ratio/.test(m))).toEqual([]);
  });
  it("the screen is a container the size rules can ask", () => {
    expect(css).toMatch(/\.screen\s*{[^}]*container:\s*screen\s*\/\s*size/);
    expect(css).toMatch(/@container screen \(max-height/);
  });
  it("viewport-height units are not used for sizing (they too ignore the address bar)", () => {
    expect(css.replace(/translateY\(110dvh\)/, "").replace(/var\(--app-h, 100dvh\)/, "").match(/\d+(\.\d+)?(dvh|svh|lvh|vh)\b/g)).toEqual(
      ["100vh"]);    // the one fallback before 100dvh, for browsers without it
  });
});
