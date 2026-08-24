"use client";

/**
 * Global notification bell.
 *
 * Lives in the page header so it sits top-right on every screen at every
 * breakpoint, rather than being buried behind the More tab.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { montra } from "@/lib/api";

function BellIcon() {
  // Lucide-style stroke icon at 22px (UI/UX section 16).
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10.268 21a2 2 0 0 0 3.464 0" />
      <path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326" />
    </svg>
  );
}

export function NotificationBell() {
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);

  // Re-checked on every navigation, so acting on a notification updates the
  // badge without a full reload.
  useEffect(() => {
    let cancelled = false;
    montra
      .notifications(true)
      .then((r) => {
        if (!cancelled) setUnread(r.data.length);
      })
      .catch(() => {
        if (!cancelled) setUnread(0);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  // No point pointing at the page you are already on.
  if (pathname === "/notifications") return null;

  const label =
    unread > 0
      ? `Notifications, ${unread} unread`
      : "Notifications";

  return (
    <Link
      href="/notifications"
      aria-label={label}
      className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-content-secondary transition hover:bg-white/5 hover:text-content-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
    >
      <BellIcon />
      {unread > 0 && (
        <span
          aria-hidden
          className="tabular absolute right-1 top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-background-primary"
        >
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </Link>
  );
}
