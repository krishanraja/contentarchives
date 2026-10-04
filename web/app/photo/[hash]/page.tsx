import Link from "next/link";
import { notFound } from "next/navigation";
import Bar from "@/components/Bar";
import { photo } from "@/lib/data";
import PhotoActions from "./PhotoActions";
import { Back } from "@/components/icons";

export const dynamic = "force-dynamic";

function when(p: { year: number | null; approx_year: string | null; taken_at: Date | null }) {
  if (p.taken_at) return new Date(p.taken_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  if (p.year) return String(p.year);
  if (p.approx_year) return `About ${p.approx_year}`;
  return null;
}

export default async function Photo({ params, searchParams }: { params: Promise<{ hash: string }>; searchParams: Promise<{ q?: string }> }) {
  const { hash } = await params;
  const q = (await searchParams).q || "";
  const p = await photo(decodeURIComponent(hash));
  if (!p) notFound();
  const w = when(p);
  const where = [p.place, p.country && p.country !== p.place ? p.country : null].filter(Boolean).join(", ");
  return (
    <>
      <Bar title="Photo" />
      <main className="page">
        <div className="hero"><img src={`/img/v/${encodeURIComponent(p.hash)}`} alt={p.description || "A family photo"} /></div>
        {p.media === "video" && <p className="notice">This is a video. The picture above is a still from it.</p>}
        <div className="card">
          <div><h3>Who</h3><p>{p.people.length ? p.people.join(", ") : <span className="muted">Nobody named yet</span>}</p></div>
          <div><h3>Where</h3><p>{where || <span className="muted">Not known yet</span>}</p></div>
          <div><h3>When</h3><p>{w || <span className="muted">Not known yet</span>}</p></div>
          {p.description && <div><h3>What</h3><p>{p.description}</p></div>}
        </div>
        <PhotoActions hash={p.hash} needs={!p.place || (!p.year && !p.approx_year)} />
        <Link className="btn block" href={q ? `/find?q=${encodeURIComponent(q)}` : "/find"}><Back /> Back to photos</Link>
      </main>
    </>
  );
}
