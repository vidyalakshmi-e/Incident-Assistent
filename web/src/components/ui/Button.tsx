"use client";

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-[3px] font-semibold whitespace-nowrap select-none " +
  "transition-[background-color,color,border-color,transform,box-shadow] duration-150 ease-out " +
  "active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0";

const variants: Record<Variant, string> = {
  primary:
    "bg-cobalt-fill text-on-cobalt hover:bg-cobalt-fill-hover shadow-[0_1px_0_hsl(var(--shade)/0.18),0_2px_6px_-2px_hsl(var(--shade)/0.35)]",
  secondary: "bg-sheet text-ink border border-line-2 hover:border-ink-3 hover:bg-paper",
  ghost: "text-ink-2 hover:bg-paper-2 hover:text-ink",
  danger: "bg-sheet text-red border border-red/55 hover:bg-red-soft hover:border-red",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13.5px]",
  md: "h-10 px-4 text-[14.5px]",
  lg: "h-11 px-5 text-[15px]",
};

export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra = "") {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`;
}

export function Busy() {
  return (
    <span aria-hidden className="relative inline-block h-[2px] w-4 overflow-hidden bg-current/30">
      <span className="absolute inset-y-0 left-0 w-1/2 bg-current animate-[sweep_0.9s_ease-in-out_infinite]" />
    </span>
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className = "",
  disabled,
  ...rest
}: ComponentProps<"button"> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClass(variant, size, className)}
    >
      {loading ? <Busy /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  children,
  className = "",
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {icon}
      {children}
    </Link>
  );
}
