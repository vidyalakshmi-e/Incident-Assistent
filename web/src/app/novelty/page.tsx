import type { Metadata } from "next";

import { NoveltyView } from "@/components/novelty/NoveltyView";

export const metadata: Metadata = { title: "Novel Incidents" };

export default function Page() {
  return <NoveltyView />;
}
