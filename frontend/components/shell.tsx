"use client";

/**
 * Application shell.
 *
 * Mobile gets a bottom navigation bar within thumb reach; desktop gets a
 * persistent sidebar (UI/UX sections 18, 20, 23, 24).
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode } from "react";

import { montra } from "@/lib/api";
import { NotificationBell } from "@/components/notification-bell";
import { Icon, IconName } from "@/components/icons";

const NAV: { href: string; label: string; icon: IconName; primary?: boolean }[] = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/accounts", label: "Accounts", icon: "wallet" },
  { href: "/add", label: "Add", icon: "plus", primary: true },
  { href: "/planning", label: "Planning", icon: "calendar" },
  { href: "/more", label: "More", icon: "more" },
];


export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

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
              <Icon name={item.icon} size={20} />
              {item.label}
            </Link>
          ))}
        </nav>
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
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-background-primary">
                  <Icon name={item.icon} size={24} strokeWidth={2.2} />
                </span>
              </Link>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className={`flex min-h-[56px] flex-1 flex-col items-center justify-center gap-1 text-[11px] ${
                  pathname === item.href ? "text-accent" : "text-content-secondary"
                }`}
              >
                <Icon name={item.icon} size={21} />
                {item.label}
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
  leading,
  icon,
}: {
  title: string;
  action?: ReactNode;
  /** Rendered before the title, e.g. a profile avatar. Wins over `icon`. */
  leading?: ReactNode;
  /** Section icon shown before the title. */
  icon?: IconName;
}) {
  return (
    <header className="mb-6 flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2 sm:gap-2.5">
        {/* Tighter on a narrow phone: this row also carries the page action
            and the bell, and the title must not be the thing that gives way. */}
        {leading ??
          (icon && (
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-muted text-accent sm:h-9 sm:w-9">
              <Icon name={icon} size={18} className="sm:hidden" />
              <Icon name={icon} size={19} className="hidden sm:block" />
            </span>
          ))}
        <h1 className="min-w-0 truncate text-title text-content-primary">{title}</h1>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {action}
        {/* Rightmost: global chrome sits outside whatever the page offers. */}
        <NotificationBell />
      </div>
    </header>
  );
}
