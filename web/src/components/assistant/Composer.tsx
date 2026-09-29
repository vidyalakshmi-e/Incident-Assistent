"use client";

import { ArrowRight } from "@phosphor-icons/react";
import { useId, type ReactNode } from "react";

import { Button } from "../ui/Button";
import { TextArea } from "../ui/Form";

export const DEMO_REPORT =
  "The application is becoming slower and sometimes freezes when users try to open records. Restarting fixes it temporarily.";

export const PRESETS: { label: string; text: string }[] = [
  { label: "Memory leak", text: DEMO_REPORT },
  { label: "Vague report", text: "the system feels slow and basic things take forever" },
  { label: "Login loop", text: "Users are sent back to the login page after entering credentials" },
  { label: "Report timeouts", text: "Reports keep loading forever and then fail with a timeout during the morning peak" },
  { label: "Printer queue", text: "Nothing comes out of the printer, documents stay in the queue" },
  { label: "Tape robot (unseen)", text: "Robotic tape library arm is jammed and the offsite tape rotation cannot be performed." },
];

export function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  submitLabel,
  presets = PRESETS,
  footer,
  label = "Incident report",
  hint = "Write it the way it was reported. Vague is fine.",
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  submitLabel: string;
  presets?: { label: string; text: string }[];
  footer?: ReactNode;
  label?: string;
  hint?: string;
}) {
  const id = useId();
  const canSubmit = value.trim().length > 3 && !busy;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onSubmit();
      }}
      className="border border-line-2 bg-sheet shadow-[0_1px_0_hsl(var(--shade)/0.04),0_8px_24px_-18px_hsl(var(--shade)/0.4)]"
    >
      <div className="flex items-baseline justify-between gap-3 px-4 pt-3.5 sm:px-5">
        <label htmlFor={id} className="text-[13.5px] font-semibold text-ink">
          {label}
        </label>
        <span className="hidden text-[12.5px] text-ink-3 sm:inline">{hint}</span>
      </div>
      <TextArea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit) onSubmit();
        }}
        rows={2}
        className="min-h-[5.2rem] resize-y rounded-none! border-0! bg-transparent! px-4 text-[17px]! shadow-none! [field-sizing:content] focus:shadow-none! sm:px-5"
        placeholder="e.g. Users in the Leeds office cannot reach the VPN since this morning"
      />
      <div className="flex flex-col gap-3 border-t border-line px-4 py-3 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[12.5px] text-ink-3">Try</span>
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => onChange(p.text)}
              aria-pressed={value === p.text}
              className={`h-7 rounded-[3px] border px-2.5 text-[12.5px] font-semibold transition-colors duration-150 active:translate-y-px ${
                value === p.text
                  ? "border-ink bg-ink text-paper"
                  : "border-line bg-paper text-ink-2 hover:border-ink-3 hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 self-end lg:self-auto">
          <span className="hidden text-[12px] text-ink-3 xl:inline">Ctrl + Enter</span>
          <Button type="submit" variant="primary" size="lg" loading={busy} disabled={!canSubmit} icon={!busy && <ArrowRight size={17} weight="bold" />}>
            {submitLabel}
          </Button>
        </div>
      </div>
      {footer}
    </form>
  );
}
