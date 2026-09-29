"use client";

import { useId, type ComponentProps, type ReactNode } from "react";

const control =
  "w-full rounded-[3px] border border-line-2 bg-sheet text-ink placeholder:text-ink-3 " +
  "transition-[border-color,box-shadow] duration-150 hover:border-ink-3 " +
  "focus:border-cobalt focus:outline-none focus:shadow-[0_0_0_3px_var(--cobalt-soft)]";

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={htmlFor} className="text-[13.5px] font-semibold text-ink">
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-[13px] text-ink-3">{hint}</p>}
      {error && <p className="text-[13px] font-medium text-red">{error}</p>}
    </div>
  );
}

export function TextArea({ className = "", ...rest }: ComponentProps<"textarea">) {
  return <textarea {...rest} className={`${control} px-3.5 py-3 text-[15.5px] leading-relaxed ${className}`} />;
}

export function Input({ className = "", ...rest }: ComponentProps<"input">) {
  return <input {...rest} className={`${control} h-10 px-3 text-[14.5px] ${className}`} />;
}

export function Select({ className = "", children, ...rest }: ComponentProps<"select">) {
  return (
    <select
      {...rest}
      className={`${control} h-10 appearance-none bg-[length:10px] bg-[right_12px_center] bg-no-repeat px-3 pr-8 text-[14.5px] ${className}`}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%2356636f' stroke-width='1.5'/%3E%3C/svg%3E\")",
      }}
    >
      {children}
    </select>
  );
}

/** Radio group drawn as a segmented control. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "md",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; tone?: "neutral" | "good" | "bad" }[];
  label: string;
  size?: "sm" | "md";
}) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex w-fit self-start rounded-[3px] border border-line-2 bg-sheet p-0.5">
      {options.map((o) => {
        const on = o.value === value;
        const tone =
          on && o.tone === "bad"
            ? "bg-red-fill text-on-red"
            : on && o.tone === "good"
              ? "bg-cobalt-fill text-on-cobalt"
              : on
                ? "bg-ink text-paper"
                : "text-ink-2 hover:bg-paper-2 hover:text-ink";
        return (
          <label
            key={o.value}
            className={`relative cursor-pointer rounded-[2px] font-semibold transition-colors duration-150 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-cobalt ${
              size === "sm" ? "px-2.5 py-1 text-[13px]" : "px-3.5 py-1.5 text-[14px]"
            } ${tone}`}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={on}
              onChange={() => onChange(o.value)}
              className="sr-only"
            />
            {o.label}
          </label>
        );
      })}
    </div>
  );
}

/** Multi-select pill toggle. */
export function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`h-8 rounded-[3px] border px-3 text-[13.5px] font-semibold transition-colors duration-150 active:translate-y-px ${
        on ? "border-ink bg-ink text-paper" : "border-line-2 bg-sheet text-ink-2 hover:border-ink-3 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

export function Checkbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2.5 text-[14px] text-ink-2 select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 accent-[var(--cobalt)]"
      />
      {children}
    </label>
  );
}
