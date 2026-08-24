"use client";

import { ReactNode } from "react";

import { SessionProvider } from "@/components/session";

export function Providers({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
