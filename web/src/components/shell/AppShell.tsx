"use client";

import { Books, ChartLineUp, CircleDashed, Compass, Graph, Headset, ThumbsUp, Wrench } from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import useSWR from "swr";

import { fetcher } from "@/lib/api";
import type { EscalationsResponse } from "@/lib/types";

import { Mark } from "./Mark";
import { StatusStation } from "./StatusStation";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  {
    group: "Operate",
    items: [
      { href: "/assistant", label: "Assistant", icon: Compass },
      { href: "/troubleshooting", label: "Troubleshooting", icon: Wrench },
      { href: "/escalations", label: "Escalations", icon: Headset },
      { href: "/novelty", label: "Novel incidents", icon: CircleDashed },
    ],
  },
  {
    group: "Understand",
    items: [
      { href: "/patterns", label: "Patterns", icon: Graph },
      { href: "/knowledge", label: "Knowledge base", icon: Books },
    ],
  },
  {
    group: "Improve",
    items: [
      { href: "/feedback", label: "Feedback", icon: ThumbsUp },
      { href: "/evaluation", label: "Evaluation", icon: ChartLineUp },
    ],
  },
];

function isActive(path: string, href: string) {
  if (href === "/assistant") return path === "/" || path.startsWith("/assistant") || path.startsWith("/incidents");
  return path.startsWith(href);
}

function Nav() {
  const path = usePathname();
  // Open escalations are work waiting for L2/L3, so their count sits in the rail.
  const esc = useSWR<EscalationsResponse>("/escalations", fetcher, { refreshInterval: 30_000 });
  const open = esc.data?.open ?? 0;
  return (
    <nav aria-label="Primary" className="flex flex-col gap-5">
      {NAV.map((g) => (
        <div key={g.group}>
          <p className="annot mb-1.5 px-2.5 text-ink-3">{g.group}</p>
          <ul className="flex flex-col gap-px">
            {g.items.map(({ href, label, icon: Icon }) => {
              const on = isActive(path, href);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={on ? "page" : undefined}
                    className={`flex h-9 items-center gap-2.5 rounded-[3px] px-2.5 text-[14.5px] transition-colors duration-150 ${
                      on
                        ? "bg-sheet font-semibold text-ink shadow-[0_1px_2px_hsl(var(--shade)/0.12)]"
                        : "text-ink-2 hover:bg-paper hover:text-ink"
                    }`}
                  >
                    <Icon size={18} weight={on ? "bold" : "regular"} className={on ? "text-cobalt" : "text-ink-3"} />
                    {label}
                    {href === "/escalations" && open > 0 && (
                      <span className="num ml-auto text-[12.5px] font-semibold text-amber-ink" aria-label={`${open} open`}>
                        {open}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/** Desktop only (no phone layout, by the owner's decision): a fixed rail and one main column. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh min-w-[1200px] grid-cols-[244px_minmax(0,1fr)] bg-[linear-gradient(to_right,var(--paper-2)_243px,var(--line)_243px,var(--line)_244px,transparent_244px)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-sheet focus:px-3 focus:py-2"
      >
        Skip to content
      </a>

      <aside className="sticky top-0 flex h-dvh flex-col justify-between gap-6 overflow-y-auto border-r border-line bg-paper-2 px-3.5 pt-5 pb-4">
        <div className="flex flex-col gap-7">
          <Link href="/assistant" className="flex items-center gap-2.5 px-1">
            <Mark />
            <span className="display text-[16.5px] font-bold leading-tight text-ink">Incident Intelligence</span>
          </Link>
          <Nav />
        </div>
        <div className="flex flex-col gap-3">
          <StatusStation />
          <p className="text-[12px] leading-snug text-ink-3">Decision support only. A human confirms anything disruptive.</p>
          <ThemeToggle />
        </div>
      </aside>

      <main id="main" className="min-w-0 px-10 pt-9 pb-24">
        <div className="mx-auto max-w-[1240px]">{children}</div>
      </main>
    </div>
  );
}
