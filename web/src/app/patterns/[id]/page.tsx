import type { Metadata } from "next";

import { FamilyView } from "@/components/patterns/FamilyView";

export async function generateMetadata({ params }: PageProps<"/patterns/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: `Family ${id}` };
}

export default async function Page({ params }: PageProps<"/patterns/[id]">) {
  const { id } = await params;
  return <FamilyView id={id} />;
}
