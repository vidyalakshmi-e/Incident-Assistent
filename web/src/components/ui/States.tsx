import { ArrowCounterClockwise } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

type Tone = "info" | "warn" | "error";

// Flat graded bands, as on a forecast-office bulletin: the grade word is printed in its own
// column, the message beside it. No icons, no rounded callout boxes.
const tones: Record<Tone, { box: string; grade: string; word: string }> = {
  info: { box: "bg-paper-2 text-ink", grade: "text-ink-2", word: "Note" },
  warn: { box: "bg-amber-soft text-ink", grade: "text-amber-ink", word: "Caution" },
  error: { box: "bg-red-soft text-ink", grade: "text-red", word: "Alert" },
};

export function Notice({
  tone = "info",
  title,
  children,
  action,
  compact = false,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  const t = tones[tone];
  const head = typeof title === "string" && !/[.!?:]$/.test(title) ? `${title}.` : title;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`grid gap-x-5 gap-y-1 sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] ${compact ? "px-4 py-2" : "px-4 py-3"} ${t.box}`}
    >
      <span className={`grade pt-[3px] ${t.grade}`}>{t.word}</span>
      <div className={`min-w-0 leading-relaxed ${compact ? "text-[13.5px]" : "text-[14px]"}`}>
        {head && <span className="font-semibold text-ink">{head}</span>}
        {head && children && (compact ? " " : <br />)}
        {children && <span className="text-ink-2">{children}</span>}
      </div>
      {action && <div className="self-center">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <Notice
      tone="error"
      title="Could not load this view."
      action={
        onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-red hover:underline"
          >
            <ArrowCounterClockwise size={15} weight="bold" /> Retry
          </button>
        )
      }
    >
      {msg}
    </Notice>
  );
}

export function Skel({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`skel ${className}`} />;
}

export function Empty({
  title,
  children,
  action,
  icon,
}: {
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-3 border border-dashed border-line-2 px-6 py-8">
      {icon && <span className="text-ink-3">{icon}</span>}
      <div>
        <p className="text-[15.5px] font-semibold text-ink">{title}</p>
        {children && <div className="mt-1 max-w-[60ch] text-[14px] text-ink-2">{children}</div>}
      </div>
      {action}
    </div>
  );
}
