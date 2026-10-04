import { PROMPT, RICH_PROMPT, SENS_PROMPT } from "./prompts";

const BASE = "https://generativelanguage.googleapis.com/v1beta/models/";
export const VISION_MODEL = "gemini-3.1-flash-lite";   // as classify_live.py
export const EMBED_MODEL = "gemini-embedding-001";     // as embed_descriptions.py
export const DIM = 768;

const key = () => process.env.GOOGLE_API_KEY_ARCHIVES || "";
export const hasGemini = () => key() !== "";

// Permissive on purpose, as classify_live.py: a filter that refuses to say
// whether there is nudity fails on exactly the images the question is for.
const SAFETY = ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
  "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
  .map((category) => ({ category, threshold: "BLOCK_NONE" }));

async function post(model: string, method: string, body: unknown, timeoutMs = 60000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${BASE}${model}:${method}`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": key() },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    if (!r.ok) throw new Error(`gemini ${method} ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

export async function embed(text: string, task = "RETRIEVAL_QUERY"): Promise<number[]> {
  const j = await post(EMBED_MODEL, "embedContent", {
    content: { parts: [{ text }] },
    taskType: task,
    outputDimensionality: DIM,
  }, 15000);
  const v: number[] = j?.embedding?.values || [];
  if (v.length !== DIM) throw new Error("embedding has the wrong shape");
  // normalise, as embed_descriptions.py does before ranking
  const n = Math.sqrt(v.reduce((a, x) => a + x * x, 0)) || 1;
  return v.map((x) => x / n);
}

function parseJson(j: any): Record<string, any> {
  const text: string = j?.candidates?.[0]?.content?.parts?.map((p: any) => p.text || "").join("") || "";
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in the model's reply");
  return JSON.parse(m[0]);
}

async function ask(prompt: string, jpeg: Buffer): Promise<Record<string, any>> {
  const j = await post(VISION_MODEL, "generateContent", {
    contents: [{ parts: [
      { inline_data: { mime_type: "image/jpeg", data: jpeg.toString("base64") } },
      { text: prompt },
    ] }],
    safetySettings: SAFETY,
    generationConfig: { temperature: 0, responseMimeType: "application/json" },
  });
  return parseJson(j);
}

// The three passes the library machine ran, in one place, on one image.
export async function classify(jpeg: Buffer) {
  const [base, rich, sens] = await Promise.all([
    ask(PROMPT, jpeg), ask(RICH_PROMPT, jpeg), ask(SENS_PROMPT, jpeg),
  ]);
  return { ...base, ...rich, ...sens };
}
