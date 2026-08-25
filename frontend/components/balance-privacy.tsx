"use client";

/**
 * Whether amounts are masked, and what remembers that.
 *
 * Two preferences, and they answer different questions:
 *
 * - "Hide balances by default" is where each session starts.
 * - "Remember balance privacy" decides whether the last choice outlives the
 *   session, or whether every session goes back to the default.
 *
 * Shared rather than per-page: hiding balances on Home and finding them
 * showing on Accounts would make the setting feel broken, which is roughly
 * what happened when each page kept its own copy.
 *
 * The remembered value is local to the device on purpose. It is a statement
 * about the room you are in, not about the account.
 */

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import { montra } from "@/lib/api";

const STORAGE_KEY = "montra.balances-hidden";

type State = {
  hidden: boolean;
  toggle: () => void;
  /** False until the preference is known, so nothing flashes the wrong way. */
  ready: boolean;
  /** Re-read the preferences, for when the settings screen has changed them. */
  refresh: () => void;
};

const BalancePrivacy = createContext<State>({
  hidden: false,
  toggle: () => {},
  ready: false,
  refresh: () => {},
});

export function BalancePrivacyProvider({ children }: { children: ReactNode }) {
  const [hidden, setHidden] = useState(false);
  const [persist, setPersist] = useState(false);
  const [ready, setReady] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    montra
      .preferences()
      .then((prefs) => {
        if (cancelled) return;
        const remembered =
          typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEY);
        setPersist(prefs.persist_balance_privacy);
        // The remembered choice only counts while the user has asked for it
        // to be remembered; otherwise every session starts at the default.
        setHidden(
          prefs.persist_balance_privacy && remembered !== null
            ? remembered === "1"
            : prefs.hide_balances,
        );
        if (!prefs.persist_balance_privacy) {
          window.localStorage.removeItem(STORAGE_KEY);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(load, [load]);

  const toggle = useCallback(() => {
    setHidden((current) => {
      const next = !current;
      if (persist && typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      }
      return next;
    });
  }, [persist]);

  return (
    <BalancePrivacy.Provider value={{ hidden, toggle, ready, refresh: load }}>
      {children}
    </BalancePrivacy.Provider>
  );
}

export function useBalancePrivacy(): State {
  return useContext(BalancePrivacy);
}
