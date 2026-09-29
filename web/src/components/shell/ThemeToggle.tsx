"use client";

import { Desktop, Moon, Sun } from "@phosphor-icons/react";
import { useSyncExternalStore } from "react";

type Theme = "system" | "light" | "dark";

// Runs before paint (inlined in <head>) so a stored choice never flashes the other theme.
export const themeScript = `try{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}`;

const EVENT = "theme-change";

function read(): Theme {
  try {
    const t = localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

function apply(t: Theme) {
  const root = document.documentElement;
  if (t === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", t);
  try {
    if (t === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", t);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, read, () => "system" as Theme);

  const opts: { v: Theme; icon: React.ReactNode; label: string }[] = [
    { v: "system", icon: <Desktop size={15} />, label: "Match system theme" },
    { v: "light", icon: <Sun size={15} />, label: "Day chart (light)" },
    { v: "dark", icon: <Moon size={15} />, label: "Night chart (dark)" },
  ];

  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex self-start rounded-[3px] border border-line bg-paper p-0.5">
      {opts.map((o) => (
        <button
          key={o.v}
          type="button"
          role="radio"
          aria-checked={theme === o.v}
          aria-label={o.label}
          title={o.label}
          onClick={() => apply(o.v)}
          className={`grid h-7 w-8 place-items-center rounded-[2px] transition-colors duration-150 ${
            theme === o.v ? "bg-sheet text-ink shadow-[0_1px_2px_hsl(var(--shade)/0.18)]" : "text-ink-3 hover:text-ink"
          }`}
        >
          {o.icon}
        </button>
      ))}
    </div>
  );
}
