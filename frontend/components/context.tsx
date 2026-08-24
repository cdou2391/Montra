"use client";

/**
 * Personal / Family context (UI/UX sections 25-27, Implementation Plan Phase 21).
 *
 * The context is a lens, not a mode: it decides which set of accounts every
 * screen is reading. It is kept here so switching on one screen carries to the
 * others, and persisted so it survives a reload — but the server is the one
 * that enforces it. This is presentation only.
 */

import { ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";

import { Context, Family, montra } from "@/lib/api";
import { Icon } from "@/components/icons";

const STORAGE_KEY = "montra.context";

type ContextState = {
  context: Context;
  setContext: (next: Context) => void;
  family: Family | null;
  loading: boolean;
  refresh: () => void;
};

const FinancialContext = createContext<ContextState>({
  context: "personal",
  setContext: () => {},
  family: null,
  loading: true,
  refresh: () => {},
});

export function useFinancialContext() {
  return useContext(FinancialContext);
}

export function FinancialContextProvider({ children }: { children: ReactNode }) {
  const [context, setContextState] = useState<Context>("personal");
  const [family, setFamily] = useState<Family | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    montra
      .currentFamily()
      .then((f) => {
        setFamily(f);
        // Leaving a household must not strand the app in a family view of
        // nothing.
        if (!f) setContextState("personal");
      })
      .catch(() => setFamily(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "family" || stored === "personal") setContextState(stored);
    refresh();
  }, [refresh]);

  const setContext = useCallback((next: Context) => {
    setContextState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  return (
    <FinancialContext.Provider value={{ context, setContext, family, loading, refresh }}>
      {children}
    </FinancialContext.Provider>
  );
}

/**
 * The switch itself. Renders nothing when the user has no household — there is
 * no second context to switch to, and an inert control is worse than none.
 */
export function ContextSwitch({ className = "" }: { className?: string }) {
  const { context, setContext, family } = useFinancialContext();
  if (!family) return null;

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label="Financial context"
        className="grid grid-cols-2 gap-1 rounded-control bg-background-secondary p-1"
      >
        {(
          [
            ["personal", "Personal"],
            ["family", "Family"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={context === value}
            onClick={() => setContext(value)}
            className={`pressable min-h-[40px] rounded-[10px] text-sm font-semibold transition ${
              context === value
                ? "bg-accent-muted text-accent"
                : "text-content-secondary"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Section 27: a quiet cue that the numbers are the household's, not a
          different theme. */}
      {context === "family" && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-content-secondary">
          <Icon name="users" size={14} className="shrink-0 text-accent" />
          Showing {family.name}
        </p>
      )}
    </div>
  );
}
