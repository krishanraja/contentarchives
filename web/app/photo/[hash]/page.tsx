import { notFound } from "next/navigation";
import Bar from "@/components/Bar";
import { photo } from "@/lib/data";
import PhotoView from "./PhotoView";

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
  const where = [p.place, p.country && p.country !== p.place ? p.country : null].filter(Boolean).join(", ");
  return (
    <>
      <Bar title="Photo" />
      <main className="page">
        <PhotoView back={q ? `/find?q=${encodeURIComponent(q)}` : "/find"} p={{
          hash: p.hash, alt: p.description || "A family photo", people: p.people, where, when: when(p),
          what: p.description || null, video: p.media === "video", needs: !p.place || (!p.year && !p.approx_year),
        }} />
      </main>
    </>
  );
}
