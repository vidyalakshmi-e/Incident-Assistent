"use client";

import { create } from "zustand";

/** A short-lived message, e.g. "New incident logged". Kept out of the persisted desk store on purpose. */
export interface Toast {
  id: number;
  title: string;
  body?: string;
  href?: string;
  hrefLabel?: string;
}

interface ToastState {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

let next = 1;

export const useToasts = create<ToastState>()((set) => ({
  toasts: [],
  push: (t) => {
    const id = next++;
    set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })), 7000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

/** Announce a freshly created incident record. */
export function announceNewIncident(incidentId: string) {
  useToasts.getState().push({
    title: "New incident logged",
    body: incidentId,
    href: `/incidents/${encodeURIComponent(incidentId)}`,
    hrefLabel: "Open record",
  });
}
