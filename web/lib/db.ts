import postgres from "postgres";
import { need } from "./env";

// One pooled client per server instance. Supabase's transaction pooler does
// not support prepared statements, so they are off.
let client: postgres.Sql | null = null;
export function sql(): postgres.Sql {
  if (!client) {
    client = postgres(need("DATABASE_URL"), {
      prepare: false,
      max: 5,
      idle_timeout: 20,
      connect_timeout: 10,
    });
  }
  return client;
}
