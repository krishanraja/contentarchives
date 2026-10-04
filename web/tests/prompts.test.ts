import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { PROMPT, RICH_PROMPT, SENS_PROMPT } from "../lib/prompts";

const root = path.join(__dirname, "../../stages/05_enrich");
const grab = (file: string, name: string) => {
  const s = readFileSync(path.join(root, file), "utf8");
  const m = s.match(new RegExp(`^${name} = """([\\s\\S]*?)"""`, "m"));
  return m ? m[1] : null;
};

// A file found on Drive later is judged by exactly the words that judged the
// first 85,000. If the library's prompt changes, this fails until both do.
describe("prompts match the library's classifier", () => {
  it("PROMPT", () => expect(PROMPT).toBe(grab("batch_classify.py", "PROMPT")));
  it("RICH_PROMPT", () => expect(RICH_PROMPT).toBe(grab("classify_live.py", "RICH_PROMPT")));
  it("SENS_PROMPT", () => expect(SENS_PROMPT).toBe(grab("classify_live.py", "SENS_PROMPT")));
});
