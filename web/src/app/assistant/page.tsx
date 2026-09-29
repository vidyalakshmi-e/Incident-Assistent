import type { Metadata } from "next";

import { AssistantView } from "@/components/assistant/AssistantView";

export const metadata: Metadata = { title: "Assistant" };

export default function Page() {
  return <AssistantView />;
}
