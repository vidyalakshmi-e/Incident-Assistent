import type { Metadata } from "next";

import { PatternsView } from "@/components/patterns/PatternsView";

export const metadata: Metadata = { title: "Patterns" };

export default function Page() {
  return <PatternsView />;
}
