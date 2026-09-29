import { CaretRight } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

export function Disclosure({
  title,
  meta,
  children,
  defaultOpen = false,
  id,
}: {
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  id?: string;
}) {
  return (
    <details id={id} className="disclosure border-t border-line" open={defaultOpen}>
      <summary className="group flex cursor-pointer items-baseline gap-3 py-4 select-none">
        <CaretRight
          size={15}
          weight="bold"
          className="chev relative top-[2px] shrink-0 text-ink-3 group-hover:text-cobalt"
        />
        <span className="text-[16.5px] font-semibold text-ink group-hover:text-cobalt">{title}</span>
        {meta && <span className="text-[13.5px] text-ink-3">{meta}</span>}
      </summary>
      <div className="pb-8 pl-[27px]">{children}</div>
    </details>
  );
}
