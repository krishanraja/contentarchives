import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { folderInfo, listTree, thumbnail } from "@/lib/drive";
import { classify, embed, hasGemini } from "@/lib/gemini";
import { syncDrive } from "@/lib/sync";
import { need } from "@/lib/env";

// 60s fits every Vercel plan; the sync stops adding at 50s and resumes tomorrow.
export const maxDuration = 60;

// Vercel Cron calls this daily with `Authorization: Bearer $CRON_SECRET`.
export async function GET(req: NextRequest) {
  if (req.headers.get("authorization") !== `Bearer ${need("CRON_SECRET")}`) {
    return new NextResponse("no", { status: 401 });
  }
  const started = Date.now();
  const folder = await folderInfo(need("DRIVE_COMMUNAL_FOLDER_ID")).catch((e) => ({ ok: false as const, error: String(e) }));
  if (!folder.ok) return NextResponse.json({ folder }, { status: 502 });
  const report = await syncDrive(sql(), {
    list: () => listTree(need("DRIVE_COMMUNAL_FOLDER_ID"), process.env.DRIVE_REL_PREFIX || "Media/Communal"),
    image: (f) => thumbnail(f.id, 1024),
    classify: hasGemini() ? classify : null,
    embed: hasGemini() ? (t) => embed(t, "RETRIEVAL_DOCUMENT") : null,
    budget: 15,
    deadline: started + 50_000,
  });
  return NextResponse.json({ folder, ...report });
}
