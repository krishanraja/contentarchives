import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { folderInfo, listTree } from "@/lib/drive";
import { need } from "@/lib/env";

// READ-ONLY health check. The index has ONE writer, stages/13_app/cloud_enrich.py
// (GitHub Actions, daily); this route only says what it can see:
// the folder, how many files Drive holds, how many are indexed or held back,
// and what the last worker run reported. Called with the cron secret.
export const maxDuration = 60;

export async function GET(req: NextRequest) {
  if (req.headers.get("authorization") !== `Bearer ${need("CRON_SECRET")}`) {
    return new NextResponse("no", { status: 401 });
  }
  const folder = await folderInfo(need("DRIVE_COMMUNAL_FOLDER_ID")).catch((e) => ({ ok: false as const, error: String(e) }));
  if (!folder.ok) return NextResponse.json({ folder }, { status: 502 });
  const files = await listTree(need("DRIVE_COMMUNAL_FOLDER_ID"), process.env.DRIVE_REL_PREFIX || "Media/Communal");
  const db = sql();
  const [c] = await db`select
      (select count(*)::int from photos) indexed,
      (select count(*)::int from held) held,
      (select count(*)::int from faces) faces,
      (select count(*)::int from queue) queue,
      (select count(*)::int from people) people`;
  const [last] = await db`select at, counts from snapshots where kind = 'drive-sync' order by at desc limit 1`;
  return NextResponse.json({
    folder, onDrive: files.length, ...c,
    waiting: Math.max(0, files.length - c.indexed - c.held),
    lastRun: last ? { at: last.at, ...last.counts } : null,
  });
}
