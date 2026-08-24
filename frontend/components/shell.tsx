"use client";

/**
 * Application shell.
 *
 * Mobile gets a bottom navigation bar within thumb reach; desktop gets a
 * persistent sidebar (UI/UX sections 18, 20, 23, 24).
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useState } from "react";

import { montra } from "@/lib/api";
import { NotificationBell } from "@/components/notification-bell";
import { Icon, IconName } from "@/components/icons";
import { BottomSheet } from "@/components/sheet";

const NAV: { href: string; label: string; icon: IconName; primary?: boolean }[] = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/accounts", label: "Accounts", icon: "wallet" },
  { href: "/add", label: "Add", icon: "plus", primary: true },
  { href: "/planning", label: "Planning", icon: "calendar" },
];

/** The rest of the app, reached by expanding the bar rather than leaving it. */
const MORE_ITEMS: { href: string; label: string; icon: IconName; hint: string }[] = [
  { href: "/profile", label: "Profile", icon: "user", hint: "Your details and preferences" },
  {
    href: "/notifications",
    label: "Notifications",
    icon: "bell",
    hint: "Reminders and alerts",
  },
  {
    href: "/family",
    label: "Household",
    icon: "users",
    hint: "Share with the people you live with",
  },
  {
    href: "/loans",
    label: "Loans",
    icon: "handshake",
    hint: "What you owe and are owed",
  },
  { href: "/transactions", label: "Activity", icon: "list", hint: "Every transaction" },
  {
    href: "/planning/recurring",
    label: "Recurring",
    icon: "repeat",
    hint: "Subscriptions and regular bills",
  },
];


export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [moreOpen, setMoreOpen] = useState(false);

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
          {[...NAV.filter((i) => !i.primary), ...MORE_ITEMS].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`pressable pressable-tint flex items-center gap-3 rounded-control px-3 py-2.5 text-sm ${
                pathname === item.href
                  ? "bg-accent-muted text-accent"
                  : "text-content-secondary"
              }`}
            >
              <Icon name={item.icon} size={20} />
              {item.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/add"
          className="pressable mt-6 flex min-h-[48px] items-center justify-center rounded-control bg-accent px-4 text-sm font-semibold text-background-primary"
        >
          Add transaction
        </Link>
        <button
          onClick={signOut}
          className="pressable mt-8 px-3 text-left text-xs text-content-muted hover:text-content-secondary"
        >
          Sign out
        </button>
      </aside>

      <div className="flex-1">
        <main className="mx-auto w-full max-w-3xl px-4 pb-32 pt-6 sm:px-6 lg:max-w-5xl lg:pb-10 lg:pt-8">
          {children}
        </main>
      </div>

      {/* Mobile bottom navigation, floating clear of the screen edge.
          The wrapper spans the width so the bar can centre, but ignores
          pointer events — otherwise the transparent gutters beside the bar
          would swallow taps meant for the content behind them. */}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden">
        <nav
          className="
            pointer-events-auto mx-auto flex max-w-lg items-stretch justify-around
            rounded-[22px] border border-white/10 bg-surface-elevated
            shadow-[0_10px_30px_-10px_rgba(0,0,0,0.7)]
          "
        >
          {NAV.map((item) =>
            item.primary ? (
              <Link
                key={item.href}
                href={item.href}
                aria-label="Add transaction"
                className="pressable flex flex-1 items-center justify-center py-2.5"
              >
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-background-primary">
                  <Icon name={item.icon} size={24} strokeWidth={2.2} />
                </span>
              </Link>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className={`pressable pressable-tint flex min-h-[60px] flex-1 flex-col items-center justify-center gap-1 rounded-[18px] text-[11px] ${
                  pathname === item.href ? "text-accent" : "text-content-secondary"
                }`}
              >
                <Icon name={item.icon} size={21} />
                {item.label}
              </Link>
            ),
          )}

          {/* More expands the bar in place rather than navigating away. */}
          <button
            onClick={() => setMoreOpen(true)}
            aria-expanded={moreOpen}
            aria-haspopup="dialog"
            className={`pressable pressable-tint flex min-h-[60px] flex-1 flex-col items-center justify-center gap-1 rounded-[18px] text-[11px] ${
              moreOpen || MORE_ITEMS.some((i) => i.href === pathname)
                ? "text-accent"
                : "text-content-secondary"
            }`}
          >
            <Icon name="more" size={21} />
            More
          </button>
        </nav>
      </div>

      <BottomSheet open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <div className="space-y-1">
          {MORE_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMoreOpen(false)}
              className={`pressable pressable-tint pressable-surface flex items-center gap-3 rounded-control px-3 py-3 ${
                pathname === item.href ? "bg-accent-muted" : ""
              }`}
            >
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
                  pathname === item.href
                    ? "bg-accent text-background-primary"
                    : "bg-white/5 text-content-secondary"
                }`}
              >
                <Icon name={item.icon} size={20} />
              </span>
              <span className="min-w-0">
                <span
                  className={`block text-sm font-medium ${
                    pathname === item.href ? "text-accent" : "text-content-primary"
                  }`}
                >
                  {item.label}
                </span>
                <span className="mt-0.5 block text-xs text-content-secondary">
                  {item.hint}
                </span>
              </span>
            </Link>
          ))}

          <button
            onClick={() => {
              setMoreOpen(false);
              void signOut();
            }}
            className="pressable pressable-surface mt-2 flex w-full items-center gap-3 rounded-control px-3 py-3 text-left"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-semantic-expense/15 text-semantic-expense">
              <Icon name="logOut" size={20} />
            </span>
            <span className="text-sm font-medium text-semantic-expense">Sign out</span>
          </button>
        </div>
      </BottomSheet>
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
