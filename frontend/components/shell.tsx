"use client";

/**
 * Application shell.
 *
 * Mobile gets a bottom navigation bar within thumb reach; desktop gets a
 * persistent sidebar (UI/UX sections 18, 20, 23, 24).
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { montra } from "@/lib/api";

const NAV = [
  { href: "/", label: "Home", icon: "◧" },
  { href: "/accounts", label: "Accounts", icon: "▤" },
  { href: "/add", label: "Add", icon: "＋", primary: true },
  { href: "/planning", label: "Planning", icon: "◔" },
  { href: "/more", label: "More", icon: "⋯" },
];

/** Unread badge, polled once per mount rather than held in global state. */
function useUnreadNotifications() {
  const [unread, setUnread] = useState(false);
  useEffect(() => {
    montra
      .notifications(true)
      .then((r) => setUnread(r.has_unread))
      .catch(() => setUnread(false));
  }, []);
  return unread;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const unread = useUnreadNotifications();

  async function signOut() {
    await montra.logout();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="min-h-dvh lg:flex">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-white/5 bg-background-secondary p-5 lg:block">
        <p className="px-2 text-title text-content-primary">Montra</p>
        <nav className="mt-8 space-y-1">
          {NAV.filter((i) => !i.primary).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-control px-3 py-2.5 text-sm transition ${
                pathname === item.href
                  ? "bg-accent-muted text-accent"
                  : "text-content-secondary hover:bg-white/5"
              }`}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/notifications"
          className={`mt-1 flex items-center gap-3 rounded-control px-3 py-2.5 text-sm transition ${
            pathname === "/notifications"
              ? "bg-accent-muted text-accent"
              : "text-content-secondary hover:bg-white/5"
          }`}
        >
          <span aria-hidden>◎</span>
          Notifications
          {unread && (
            <span
              aria-label="unread"
              className="ml-auto h-2 w-2 rounded-full bg-accent"
            />
          )}
        </Link>

        <Link
          href="/add"
          className="mt-6 flex min-h-[48px] items-center justify-center rounded-control bg-accent px-4 text-sm font-semibold text-background-primary"
        >
          Add transaction
        </Link>
        <button
          onClick={signOut}
          className="mt-8 px-3 text-xs text-content-muted hover:text-content-secondary"
        >
          Sign out
        </button>
      </aside>

      <div className="flex-1">
        <main className="mx-auto w-full max-w-3xl px-4 pb-28 pt-6 sm:px-6 lg:max-w-5xl lg:pb-10 lg:pt-8">
          {children}
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-white/5 bg-background-secondary/95 pb-safe backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-lg items-stretch justify-around">
          {NAV.map((item) =>
            item.primary ? (
              <Link
                key={item.href}
                href={item.href}
                aria-label="Add transaction"
                className="flex flex-1 items-center justify-center py-2"
              >
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-2xl leading-none text-background-primary">
                  {item.icon}
                </span>
              </Link>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className={`relative flex min-h-[56px] flex-1 flex-col items-center justify-center gap-1 text-[11px] ${
                  pathname === item.href ? "text-accent" : "text-content-secondary"
                }`}
              >
                <span aria-hidden className="text-lg leading-none">
                  {item.icon}
                </span>
                {item.label}
                {item.href === "/more" && unread && (
                  <span
                    aria-label="unread notifications"
                    className="absolute right-[22%] top-2 h-2 w-2 rounded-full bg-accent"
                  />
                )}
              </Link>
            ),
          )}
        </div>
      </nav>
    </div>
  );
}

export function PageHeader({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex items-center justify-between gap-4">
      <h1 className="text-title text-content-primary">{title}</h1>
      {action}
    </header>
  );
}
