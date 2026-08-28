"use client";

/** Session restoration and route protection. */

import { useRouter } from "next/navigation";
import { ReactNode, createContext, useContext, useEffect, useState } from "react";

import { CurrentUser, montra } from "@/lib/api";

type SessionState = { user: CurrentUser | null; loading: boolean; refresh: () => void };

const SessionContext = createContext<SessionState>({
  user: null,
  loading: true,
  refresh: () => {},
});

export function useSession() {
  return useContext(SessionContext);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    montra
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <SessionContext.Provider value={{ user, loading, refresh: load }}>
      {children}
    </SessionContext.Provider>
  );
}

/** Redirects to /login when no valid session cookie is present. */
export function RequireSession({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  // The page renders while the session is still being restored, rather than
  // being replaced by a placeholder of its own.
  //
  // Every page already handles its data not having arrived, and its skeleton
  // is shaped like the page. Blocking here put a second, differently shaped
  // one in front of it, so a refresh showed two unrelated loading states one
  // after the other before anything real appeared.
  //
  // Nothing is exposed by rendering early: without a session the requests
  // come back empty and the redirect below fires as soon as /me resolves,
  // which is no later than the block used to lift.
  if (!loading && !user) return null;
  return <>{children}</>;
}
