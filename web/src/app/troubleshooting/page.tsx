import type { Metadata } from "next";

import { TroubleshootingView } from "@/components/troubleshooting/TroubleshootingView";

export const metadata: Metadata = { title: "Troubleshooting" };

export default function Page() {
  return <TroubleshootingView />;
}
