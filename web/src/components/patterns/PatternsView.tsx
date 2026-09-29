"use client";

import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { clean, familyParts, int } from "@/lib/format";
import type { PatternsResponse } from "@/lib/types";

import { IdLink } from "../ui/IdLink";
import { PageHeader } from "../ui/Page";
import { ErrorState, Skel } from "../ui/States";
import { Table } from "../ui/Table";

export function PatternsView() {
  const { data, error, mutate } = useSWR<PatternsResponse>("/patterns", fetcher);

  const header = (
    <PageHeader
      title="Incident Patterns"
      lede="Recurring incident families found in the history. Open a family to see its members."
    />
  );
  if (error) return (<>{header}<ErrorState error={error} onRetry={() => mutate()} /></>);
  if (!data)
    return (
      <>
        {header}
        <div className="flex flex-col gap-2" aria-busy>
          {Array.from({ length: 10 }, (_, i) => (
            <Skel key={i} className="h-9 w-full" />
          ))}
        </div>
      </>
    );

  return (
    <>
      {header}
      <Table
        rows={data.families}
        rowKey={(f) => f.family_id}
        cols={[
          { key: "id", head: "Family", cell: (f) => <IdLink id={f.family_id} /> },
          { key: "rc", head: "Root cause", cell: (f) => <span className="font-medium">{clean(familyParts(f.name).rootCause)}</span> },
          { key: "sc", head: "Scope", cell: (f) => <span className="text-ink-2">{familyParts(f.name).scope}</span> },
          { key: "n", head: "Incidents", align: "right", cell: (f) => int(f.size) },
        ]}
      />
    </>
  );
}
