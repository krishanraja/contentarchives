import { players } from "@/lib/data";
import WhoPicker from "./WhoPicker";

export const dynamic = "force-dynamic";

export default async function Who() {
  const names = await players();
  return (
    <main className="page" style={{ paddingTop: 32 }}>
      <h1>{names.length ? "Hello! Who are you?" : "Hello! What's your name?"}</h1>
      <p className="muted">So we know who helped. You only do this once on this phone.</p>
      <WhoPicker names={names} />
    </main>
  );
}
