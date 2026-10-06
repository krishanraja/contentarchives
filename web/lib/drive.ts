import { SignJWT, importPKCS8 } from "jose";
import { need } from "./env";

// Google Drive, read as a service account that has Viewer on the Communal
// folder ONLY. It cannot see anything else in the account, which is the point.
const SCOPE = "https://www.googleapis.com/auth/drive.readonly";
let cached: { token: string; until: number } | null = null;

export async function driveToken(): Promise<string> {
  if (cached && cached.until > Date.now() + 60_000) return cached.token;
  const sa = JSON.parse(need("GOOGLE_SERVICE_ACCOUNT_JSON"));
  const k = await importPKCS8(sa.private_key, "RS256");
  const now = Math.floor(Date.now() / 1000);
  const assertion = await new SignJWT({ scope: SCOPE })
    .setProtectedHeader({ alg: "RS256", typ: "JWT" })
    .setIssuer(sa.client_email).setAudience("https://oauth2.googleapis.com/token")
    .setIssuedAt(now).setExpirationTime(now + 3600).sign(k);
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion,
    }),
  });
  if (!r.ok) throw new Error(`drive token ${r.status}`);
  const j = await r.json();
  cached = { token: j.access_token, until: Date.now() + j.expires_in * 1000 };
  return cached.token;
}

async function api(path: string, params: Record<string, string>) {
  const u = new URL("https://www.googleapis.com/drive/v3/" + path);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  const r = await fetch(u, { headers: { authorization: `Bearer ${await driveToken()}` } });
  if (!r.ok) throw new Error(`drive ${path} ${r.status}`);
  return r;
}

export type DriveFile = {
  id: string; name: string; mimeType: string; md5Checksum?: string;
  size?: string; relPath: string;
};

const FOLDER = "application/vnd.google-apps.folder";

// Every media file under the folder, with its path relative to ContentLibrary
// (prefix + the folders walked), so it can be matched to the seeded index.
export async function listTree(rootId: string, prefix: string): Promise<DriveFile[]> {
  const out: DriveFile[] = [];
  const stack: [string, string][] = [[rootId, prefix]];
  while (stack.length) {
    const [id, rel] = stack.pop()!;
    let pageToken = "";
    do {
      const r = await api("files", {
        q: `'${id}' in parents and trashed = false`,
        fields: "nextPageToken, files(id, name, mimeType, md5Checksum, size)",
        pageSize: "1000",
        supportsAllDrives: "true", includeItemsFromAllDrives: "true",
        ...(pageToken ? { pageToken } : {}),
      });
      const j = await r.json();
      for (const f of j.files || []) {
        const p = rel ? `${rel}/${f.name}` : f.name;
        if (f.mimeType === FOLDER) stack.push([f.id, p]);
        else if (/^(image|video)\//.test(f.mimeType)) out.push({ ...f, relPath: p });
      }
      pageToken = j.nextPageToken || "";
    } while (pageToken);
  }
  return out;
}

// The folder itself, before anything is listed in it. A listing of a folder
// the service account cannot see comes back EMPTY, not as an error - so "0
// files" would read as "nothing on Drive" when the truth is "not shared".
export async function folderInfo(id: string): Promise<{ ok: true; name: string; owner?: string } | { ok: false; error: string }> {
  const u = new URL("https://www.googleapis.com/drive/v3/files/" + id);
  u.searchParams.set("fields", "id, name, mimeType, owners(emailAddress), driveId");
  u.searchParams.set("supportsAllDrives", "true");
  const r = await fetch(u, { headers: { authorization: `Bearer ${await driveToken()}` } });
  if (r.status === 404) {
    // The account's EMAIL, never its key: it is what Krish has to share with.
    let who = "the service account";
    try { who = JSON.parse(need("GOOGLE_SERVICE_ACCOUNT_JSON")).client_email || who; } catch { /* named generically */ }
    return { ok: false, error: `${who} cannot see folder ${id} - share it with that email as Viewer, or check the id` };
  }
  if (!r.ok) return { ok: false, error: `drive ${r.status}: ${(await r.text()).slice(0, 200)}` };
  const j = await r.json();
  if (j.mimeType !== FOLDER) return { ok: false, error: `${j.name} is not a folder` };
  return { ok: true, name: j.name, owner: j.owners?.[0]?.emailAddress };
}

// Drive's own rendering at the size asked for. Works for HEIC and video,
// which is why this is tried before downloading the original.
export async function thumbnail(fileId: string, px: number): Promise<Buffer | null> {
  const r = await api(`files/${fileId}`, { fields: "thumbnailLink, hasThumbnail" });
  const j = await r.json();
  if (!j.thumbnailLink) return null;
  const link = String(j.thumbnailLink).replace(/=s\d+(-[a-z]+)?$/, `=s${px}`);
  const t = await fetch(link, { headers: { authorization: `Bearer ${await driveToken()}` } });
  if (!t.ok) return null;
  return Buffer.from(await t.arrayBuffer());
}

// A span of a file's bytes, straight from Drive, for a video being played.
// Drive answers a Range with 206 and its own Content-Range (which carries the
// file's whole size); the caller passes both on.
export async function mediaRange(fileId: string, from: number, to: number): Promise<Response> {
  const u = new URL(`https://www.googleapis.com/drive/v3/files/${fileId}`);
  u.searchParams.set("alt", "media");
  u.searchParams.set("supportsAllDrives", "true");
  return fetch(u, { headers: { authorization: `Bearer ${await driveToken()}`, range: `bytes=${from}-${to}` } });
}

export async function download(fileId: string): Promise<Buffer> {
  const r = await api(`files/${fileId}`, { alt: "media" });
  return Buffer.from(await r.arrayBuffer());
}
