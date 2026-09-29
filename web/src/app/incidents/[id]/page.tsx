import type { Metadata } from "next";

import { IncidentView } from "@/components/incident/IncidentView";

export async function generateMetadata({ params }: PageProps<"/incidents/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: decodeURIComponent(id) };
}

export default async function Page({ params }: PageProps<"/incidents/[id]">) {
  const { id } = await params;
  return <IncidentView id={decodeURIComponent(id)} />;
}
