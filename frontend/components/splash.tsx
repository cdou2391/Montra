"use client";

/**
 * The screen between signing in and the app being usable.
 *
 * Two rules keep this from being theatre:
 *
 * It is tied to real readiness, not a timer. It clears when the session and
 * the display preferences have actually arrived — a splash that sits for two
 * seconds while the data was ready in two hundred milliseconds is a downgrade
 * dressed as polish.
 *
 * It has a floor and a ceiling. Below the floor it would flash, which reads as
 * a glitch rather than a greeting. Above the ceiling a stalled request would
 * trap someone behind a logo with no way forward, so it gives up and lets them
 * see the app — skeletons and all — rather than holding the door shut.
 */

import { useEffect, useState } from "react";

import { Logo } from "@/components/logo";
import { useBalancePrivacy } from "@/components/balance-privacy";
import { useSession } from "@/components/session";

export const SPLASH_FLAG = "montra.splash";

const MINIMUM_MS = 500;
const CEILING_MS = 4000;
const FADE_MS = 260;

export function SignInSplash() {
  const { loading } = useSession();
  const { ready } = useBalancePrivacy();
  const [showing, setShowing] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [startedAt, setStartedAt] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.sessionStorage.getItem(SPLASH_FLAG) !== "1") return;
    // Consumed on sight: a reload later in the session is not a sign-in.
    window.sessionStorage.removeItem(SPLASH_FLAG);
    setShowing(true);
    setStartedAt(Date.now());
  }, []);

  const appReady = !loading && ready;

  useEffect(() => {
    if (!showing) return;

    const dismiss = () => {
      setLeaving(true);
      window.setTimeout(() => setShowing(false), FADE_MS);
    };

    const elapsed = Date.now() - startedAt;
    if (appReady) {
      const wait = Math.max(0, MINIMUM_MS - elapsed);
      const timer = window.setTimeout(dismiss, wait);
      return () => window.clearTimeout(timer);
    }

    // Nothing arrived in time. Show them the app rather than the logo.
    const bail = window.setTimeout(dismiss, Math.max(0, CEILING_MS - elapsed));
    return () => window.clearTimeout(bail);
  }, [showing, appReady, startedAt]);

  if (!showing) return null;

  return (
    <div
      // aria-hidden: the app behind it is what a screen reader should be
      // reading, and this says nothing a user needs.
      aria-hidden
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-background-primary transition-opacity motion-reduce:transition-none ${
        leaving ? "opacity-0" : "opacity-100"
      }`}
      style={{ transitionDuration: `${FADE_MS}ms` }}
    >
      <Logo size={72} />
      <p className="mt-5 text-title text-content-primary">Montra</p>
      <div className="mt-8 h-1 w-24 overflow-hidden rounded-full bg-white/10">
        {/* A moving bar rather than a percentage: we do not know how far along
            this is, and inventing a number would be a lie. */}
        <div className="h-full w-1/3 animate-splash-sweep rounded-full bg-accent" />
      </div>
    </div>
  );
}
