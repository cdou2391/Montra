"use client";

/** Session restoration and route protection (Implementation Plan Phase 2). */

import { useRouter } from "next/navigation";
import { ReactNode, createContext, useContext, useEffect, useState } from "react";

import { CurrentUser, montra } from "@/lib/api";
import { Skeleton } from "@/components/ui";

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

  if (loading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }
  if (!user) return null;
  return <>{children}</>;
}
