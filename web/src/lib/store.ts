"use client";

import { useEffect, useSyncExternalStore } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { AgentMessage, Analysis, KbUpdate, Postmortem, QueryEvaluation, SearchResult, TSession } from "./types";

/** One evaluated query, kept for the Evaluation page. */
export interface EvalLogEntry {
  id: string;
  text: string;
  at: string;
  from: "assistant" | "evaluation";
  evaluation: QueryEvaluation;
}

// Cross-page working state for one demo session (sessionStorage: survives reloads, not tabs).
interface DeskState {
  reportText: string;
  analysis: Analysis | null;
  session: TSession | null;
  sessionMessages: AgentMessage[];
  tsPrefill: { incidentId: string | null; text: string } | null;
  feedbackPrefill: { incidentId: string; sessionId?: string; supporting?: string[] } | null;
  postmortem: { postmortem: Postmortem; kb_update: KbUpdate | null } | null;
  novelty: { text: string; result: SearchResult } | null;
  evalLog: EvalLogEntry[];
  set: (patch: Partial<Omit<DeskState, "set" | "logEval">>) => void;
  /** Newest first; capped so sessionStorage stays small. */
  logEval: (entry: Omit<EvalLogEntry, "id" | "at">) => void;
}

export const useDesk = create<DeskState>()(
  persist(
    (set) => ({
      reportText: "",
      analysis: null,
      session: null,
      sessionMessages: [],
      tsPrefill: null,
      feedbackPrefill: null,
      postmortem: null,
      novelty: null,
      evalLog: [],
      set: (patch) => set(patch),
      logEval: (entry) =>
        set((s) => {
          const at = new Date().toISOString();
          return { evalLog: [{ ...entry, id: `${at}-${s.evalLog.length}`, at }, ...s.evalLog].slice(0, 50) };
        }),
    }),
    {
      name: "incident-desk",
      storage: createJSONStorage(() => sessionStorage),
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      partialize: ({ set, logEval, ...rest }) => rest,
      skipHydration: true,
    },
  ),
);

/** True once the session store has been read back from sessionStorage (client only). */
export function useDeskReady(): boolean {
  const ready = useSyncExternalStore(
    (cb) => useDesk.persist.onFinishHydration(cb),
    () => useDesk.persist.hasHydrated(),
    () => false,
  );
  useEffect(() => {
    if (!useDesk.persist.hasHydrated()) void useDesk.persist.rehydrate();
  }, []);
  return ready;
}
