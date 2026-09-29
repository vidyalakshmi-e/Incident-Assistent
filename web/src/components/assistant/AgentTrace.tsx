import { clean, clock } from "@/lib/format";
import type { AgentMessage } from "@/lib/types";

const who = (s: string) => s.replace(/_agent$/, "").replace(/_/g, " ");

export function AgentMessages({ messages }: { messages: AgentMessage[] }) {
  if (!messages.length) return <p className="text-[14px] text-ink-3">No agent messages were exchanged.</p>;
  return (
    <ol className="flex flex-col gap-2.5">
      {messages.map((m, i) => (
        <li key={i} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 text-[14px]">
          <span className="num font-mono text-[12px] text-ink-3">{clock(m.at)}</span>
          <span>
            <span className="font-semibold text-ink">{who(m.sender)}</span>
            <span className="text-ink-3"> to </span>
            <span className="font-semibold text-ink">{who(m.recipient)}</span>
            <span className="ml-2 font-mono text-[12px] text-cobalt">{m.intent}</span>
            <span className="block text-ink-2">{clean(m.summary)}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
