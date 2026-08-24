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
import { Icon } from "@/components/icons";

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
      <Icon name="bell" />
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
