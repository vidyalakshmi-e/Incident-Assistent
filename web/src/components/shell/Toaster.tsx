"use client";

import { CheckCircle, X } from "@phosphor-icons/react";
import Link from "next/link";

import { useToasts } from "@/lib/toast";

/** Bottom-right stack of transient messages. A new incident slides in with a cobalt edge and fades on its own. */
export function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div aria-live="polite" className="pointer-events-none fixed right-6 bottom-6 z-50 flex w-[340px] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className="toast-in pointer-events-auto flex items-start gap-3 border border-line-2 border-l-[4px] border-l-cobalt bg-sheet py-3 pr-2 pl-3.5 shadow-[0_10px_28px_-14px_hsl(var(--shade)/0.55)]"
        >
          <CheckCircle size={20} weight="fill" className="mt-px shrink-0 text-cobalt" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-semibold text-ink">{t.title}</p>
            {t.body && <p className="mt-0.5 font-mono text-[12.5px] break-all text-ink-2">{t.body}</p>}
            {t.href && (
              <Link href={t.href} onClick={() => dismiss(t.id)} className="mt-1.5 inline-block text-[13px] font-semibold text-cobalt hover:underline">
                {t.hrefLabel ?? "Open"}
              </Link>
            )}
          </div>
          <button
            type="button"
            onClick={() => dismiss(t.id)}
            aria-label="Dismiss"
            className="grid size-7 shrink-0 place-items-center rounded-[3px] text-ink-3 hover:bg-paper-2 hover:text-ink"
          >
            <X size={14} weight="bold" />
          </button>
        </div>
      ))}
    </div>
  );
}
