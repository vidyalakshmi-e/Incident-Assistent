import type { Metadata } from "next";

import { EscalationsView } from "@/components/escalations/EscalationsView";

export const metadata: Metadata = { title: "Escalations" };

export default function Page() {
  return <EscalationsView />;
}
