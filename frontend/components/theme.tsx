"use client";

/**
 * Light, dark, or whatever the device says.
 *
 * The choice is stored on the account so it travels to a new phone, and
 * mirrored to localStorage so the very first paint can honour it — see the
 * inline script in the root layout. Waiting for the preference to arrive over
 * the network would mean a flash of the wrong theme on every load, which is
 * worse than the setting is useful.
 *
 * "System" is a real third state rather than a default, because a person who
 * has their phone on a schedule wants the app to follow it.
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

export type Theme = "SYSTEM" | "LIGHT" | "DARK";

export const THEME_KEY = "montra.theme";

type State = {
  theme: Theme;
  setTheme: (next: Theme) => void;
};

const ThemeContext = createContext<State>({ theme: "SYSTEM", setTheme: () => {} });

/** Resolve SYSTEM against the device, and stamp the result on <html>. */
function apply(theme: Theme) {
  if (typeof document === "undefined") return;
  const dark =
    theme === "DARK" ||
    (theme === "SYSTEM" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  // Keeps the browser's own chrome — form controls, scrollbars — in step.
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("SYSTEM");

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_KEY) as Theme | null;
    if (stored) {
      setThemeState(stored);
      apply(stored);
    }
    // The account is the source of truth; local storage is only how the first
    // paint knows what to do.
    montra
      .preferences()
      .then((prefs) => {
        const fromAccount = (prefs.theme ?? "SYSTEM") as Theme;
        setThemeState(fromAccount);
        window.localStorage.setItem(THEME_KEY, fromAccount);
        apply(fromAccount);
      })
      .catch(() => undefined);
  }, []);

  // Following the device means following it as it changes, not only at load.
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (theme === "SYSTEM") apply("SYSTEM");
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    // Applied before the request: the switch should feel immediate, and a
    // failed save is not a reason to sit on the old theme.
    setThemeState(next);
    window.localStorage.setItem(THEME_KEY, next);
    apply(next);
    montra.updatePreferences({ theme: next }).catch(() => undefined);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): State {
  return useContext(ThemeContext);
}
