import { players } from "@/lib/data";
import WhoPicker from "./WhoPicker";

export const dynamic = "force-dynamic";

export default async function Who() {
  const names = await players();
  return (
    <main className="page" style={{ paddingTop: 32 }}>
      <h1>Hello! Who are you?</h1>
      <p className="muted">So we know who helped. You only do this once.</p>
      <WhoPicker names={names} />
    </main>
  );
}
