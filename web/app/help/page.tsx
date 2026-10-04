import Bar from "@/components/Bar";
import NameGame from "./NameGame";

export default function Help() {
  return (
    <>
      <Bar title="Who is this?" />
      <main className="page"><NameGame /></main>
    </>
  );
}
