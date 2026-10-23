import { NextRequest, NextResponse } from "next/server";
import { forgetLists } from "@/lib/data";
import { me } from "@/lib/me";
import { different, isOwner, respell, stillPair } from "@/lib/respell";

// The owner's answer to one pair on /spelling, as a plain form (it works before
// the page's script arrives), answered with the next pair. Anyone else is told
// there is nothing here.
export async function POST(req: NextRequest) {
  const who = await me();
  if (!(await isOwner(who))) return new NextResponse("Not found", { status: 404 });
  const form = await req.formData().catch(() => null);
  const get = (k: string) => String(form?.get(k) || "").trim();
  const go = (to: string) => NextResponse.redirect(new URL(to, req.url), 303);
  const a = get("a"), b = get("b"), op = get("op");
  if (!(await stillPair(a, b))) return go("/spelling");
  if (op === "different") {
    await different(who!, a, b);
    return go("/spelling");
  }
  const keep = get("keep");
  if (op !== "same" || (keep !== a && keep !== b)) return go("/spelling");
  const wrong = keep === a ? b : a;
  const out = await respell(who!, wrong, keep);
  forgetLists();      // Home and Find stop offering the wrong spelling at once
  return go(`/spelling?kept=${encodeURIComponent(keep)}&was=${encodeURIComponent(wrong)}&n=${out.photos}`);
}
