import type { Metadata } from "next";

import { EvaluationView } from "@/components/evaluation/EvaluationView";

export const metadata: Metadata = { title: "Evaluation" };

export default function Page() {
  return <EvaluationView />;
}
