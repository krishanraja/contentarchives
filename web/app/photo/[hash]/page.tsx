import { notFound } from "next/navigation";
import Bar from "@/components/Bar";
import { photo } from "@/lib/data";
import { whenLabel } from "@/lib/when";
import PhotoView from "./PhotoView";

export const dynamic = "force-dynamic";

const day = (d: Date) => new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

// What the family said wins over the date in the file (migration 0011): a scan
// or a copy carries the day it was made, not the day the picture was.
function when(p: { family_when: string | null; year: number | null; approx_year: string | null; taken_at: Date | null }) {
  if (p.family_when) return whenLabel(p.family_when);
  if (p.taken_at) return day(p.taken_at);
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
  const back = q ? `/find?q=${encodeURIComponent(q)}` : "/find";
  return (
    <>
      <Bar title="Photo" back={{ href: back, label: "Back to photos" }} />
      <main className="page">
        <PhotoView q={q} p={{
          hash: p.hash, alt: p.description || "A family photo", people: p.people, where, when: when(p),
          what: p.description || null, video: p.media === "video", play: p.play,
          needs: !p.place || (!p.year && !p.approx_year && !p.family_when),
          sameDay: p.sameDay, dayText: p.taken_at ? day(p.taken_at) : null,
        }} />
      </main>
    </>
  );
}
