import type { Metadata } from "next";

import { KnowledgeView } from "@/components/knowledge/KnowledgeView";

export const metadata: Metadata = { title: "Knowledge Base" };

export default function Page() {
  return <KnowledgeView />;
}
