import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { listTree, thumbnail } from "@/lib/drive";
import { classify, embed, hasGemini } from "@/lib/gemini";
import { syncDrive } from "@/lib/sync";
import { need } from "@/lib/env";

export const maxDuration = 300;

// Vercel Cron calls this daily with `Authorization: Bearer $CRON_SECRET`.
export async function GET(req: NextRequest) {
  if (req.headers.get("authorization") !== `Bearer ${need("CRON_SECRET")}`) {
    return new NextResponse("no", { status: 401 });
  }
  const started = Date.now();
  const report = await syncDrive(sql(), {
    list: () => listTree(need("DRIVE_COMMUNAL_FOLDER_ID"), process.env.DRIVE_REL_PREFIX || "Media/Communal"),
    image: (f) => thumbnail(f.id, 1024),
    classify: hasGemini() ? classify : null,
    embed: hasGemini() ? (t) => embed(t, "RETRIEVAL_DOCUMENT") : null,
    budget: 60,
    deadline: started + 240_000,
  });
  return NextResponse.json(report);
}
