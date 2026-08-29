"use client";

/**
 * Application shell.
 *
 * Mobile gets a bottom navigation bar within thumb reach; desktop gets a
 * persistent sidebar (UI/UX sections 18, 20, 23, 24).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useState } from "react";

import { montra } from "@/lib/api";
import { NotificationBell } from "@/components/notification-bell";
import { Icon, IconName } from "@/components/icons";
import { Logo } from "@/components/logo";
import { BottomSheet } from "@/components/sheet";
import { SigningOut, useSignOut } from "@/components/splash";

const NAV: { href: string; label: string; icon: IconName; primary?: boolean }[] = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/accounts", label: "Accounts", icon: "wallet" },
  { href: "/add", label: "Add", icon: "plus", primary: true },
  { href: "/planning", label: "Planning", icon: "calendar" },
];

/** The rest of the app, reached by expanding the bar rather than leaving it. */
const MORE_ITEMS: { href: string; label: string; icon: IconName }[] = [
  { href: "/profile", label: "Profile", icon: "user" },
  {
    href: "/settings",
    label: "App settings",
    icon: "settings",
  },
  {
    href: "/notifications",
    label: "Notifications",
    icon: "bell",
  },
  {
    href: "/family",
    label: "Household",
    icon: "users",
  },
  {
    href: "/loans",
    label: "Loans",
    icon: "handshake",
  },
  { href: "/transactions", label: "Transactions", icon: "list" },
  {
    href: "/budgets",
    label: "Budgets",
    icon: "scale",
  },
  {
    href: "/goals",
    label: "Goals",
    icon: "piggyBank",
  },
  {
    href: "/planning/forecast",
    label: "Forecast",
    icon: "trendingUp",
  },
  {
    href: "/planning/recurring",
    label: "Recurring",
    icon: "repeat",
  },
];


export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const { signOut, signingOut } = useSignOut();


  if (signingOut) return <SigningOut />;

  return (
    <div className="min-h-dvh lg:flex">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-line/5 bg-background-secondary p-5 lg:block">
        <div className="flex items-center gap-2.5 px-2">
          <Logo size={28} />
          <p className="text-title text-content-primary">Montra</p>
        </div>
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
          className="pressable mt-6 flex min-h-[44px] items-center justify-center rounded-control bg-accent px-4 text-sm font-semibold text-background-primary"
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
      <div
        className={`pointer-events-none fixed inset-x-0 bottom-0 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden ${
          // Above the sheet's backdrop while More is open, so the bar keeps its
          // own colour and the two read as one stacked surface.
          moreOpen ? "z-50" : "z-20"
        }`}
      >
        <nav
          className="
            pointer-events-auto mx-auto flex max-w-lg items-stretch justify-around
            rounded-[22px] border border-line/10 bg-surface-elevated
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

          {/* More expands the bar in place rather than navigating away, so the
              icon is a direction rather than a symbol: up means there is more
              above this, down means tap to put it away. One chevron rotated
              rather than two icons, so the change is a movement the eye can
              follow instead of a swap it has to notice. */}
          <button
            onClick={() => setMoreOpen((v) => !v)}
            aria-expanded={moreOpen}
            aria-haspopup="dialog"
            className={`pressable pressable-tint flex min-h-[60px] flex-1 flex-col items-center justify-center gap-1 rounded-[18px] text-[11px] ${
              moreOpen || MORE_ITEMS.some((i) => i.href === pathname)
                ? "text-accent"
                : "text-content-secondary"
            }`}
          >
            <Icon
              name="chevronUp"
              size={21}
              className={`motion-safe:transition-transform motion-safe:duration-200 ${
                moreOpen ? "rotate-180" : ""
              }`}
            />
            More
          </button>
        </nav>
      </div>

      <BottomSheet
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        title="More"
        variant="nav"
      >
        {/* The same tile as a bar item — icon over label, 11px, one accent
            colour for the current page — so the panel reads as more of the
            bar rather than a different kind of menu. Four across is what
            keeps the tiles the width of a thumb on the narrowest phone. */}
        <div className="grid grid-cols-4 gap-0.5">
          {MORE_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMoreOpen(false)}
              className={`pressable pressable-tint flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-[18px] px-1 py-2 text-center text-[11px] leading-tight ${
                pathname === item.href ? "bg-accent-muted text-accent" : "text-content-secondary"
              }`}
            >
              <Icon name={item.icon} size={21} />
              {item.label}
            </Link>
          ))}

          {/* Last tile rather than a row of its own: it is the same kind of
              thing, and the colour already says it is the destructive one. */}
          <button
            onClick={() => {
              setMoreOpen(false);
              void signOut();
            }}
            className="pressable pressable-tint flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-[18px] px-1 py-2 text-center text-[11px] leading-tight text-semantic-expense"
          >
            <Icon name="logOut" size={21} />
            Sign out
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
