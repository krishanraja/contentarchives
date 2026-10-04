import Bar from "@/components/Bar";
import StoryGame from "./StoryGame";

export default async function Story({ searchParams }: { searchParams: Promise<{ photo?: string }> }) {
  const photo = (await searchParams).photo || null;
  return (
    <>
      <Bar title="Where and when?" />
      <main className="page"><StoryGame only={photo} /></main>
    </>
  );
}
