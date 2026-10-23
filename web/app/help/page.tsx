import Bar from "@/components/Bar";
import NameGame from "./NameGame";

export default async function Help({ searchParams }: { searchParams: Promise<{ g?: string }> }) {
  const { g } = await searchParams;   // the face Home showed, asked first
  return (
    <>
      <Bar title="Who is this?" />
      <main className="page"><NameGame first={g || null} /></main>
    </>
  );
}
