import type { Metadata } from "next";

import { FeedbackView } from "@/components/feedback/FeedbackView";

export const metadata: Metadata = { title: "Feedback" };

export default function Page() {
  return <FeedbackView />;
}
