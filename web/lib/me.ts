import { cookies } from "next/headers";
import { COOKIE, verify } from "./session";

// Who is asking, for answers' provenance. Middleware already proved the code.
export async function me(): Promise<string | null> {
  const s = await verify((await cookies()).get(COOKIE)?.value);
  return s?.who || null;
}
