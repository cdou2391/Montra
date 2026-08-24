"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppNotification, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatDateTime } from "@/lib/format";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui";

function Notifications() {
  const [rows, setRows] = useState<AppNotification[] | null>(null);

  const load = useCallback(() => {
    montra
      .notifications()
      .then((r) => setRows(r.data))
      .catch(() => setRows([]));
  }, []);
  useEffect(load, [load]);

  async function markAll() {
    await montra.markAllNotificationsRead();
    load();
  }

  const unread = (rows ?? []).filter((n) => n.read_at === null).length;

  return (
    <AppShell>
      <PageHeader
        title="Notifications"
        icon="bell"
        action={
          unread > 0 ? (
            <Button variant="secondary" onClick={markAll}>
              Mark all read
            </Button>
          ) : undefined
        }
      />

      {rows === null ? (
        <Skeleton className="h-48 w-full" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing yet"
          message="Reminders for upcoming bills and income will appear here."
        />
      ) : (
        <Card>
          {rows.map((n) => {
            // Deep link straight to the thing the notification is about.
            const href =
              n.related_entity_type === "PLANNED_TRANSACTION" ? "/planning" : null;
            const inner = (
              <div className="flex items-start gap-3 border-b border-white/5 py-4 last:border-0">
                <span
                  aria-hidden
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    n.read_at === null ? "bg-accent" : "bg-transparent"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-content-primary">{n.title}</p>
                  <p className="tabular mt-0.5 text-sm text-content-secondary">{n.body}</p>
                  <p className="mt-1 text-xs text-content-muted">
                    {formatDateTime(n.created_at)}
                  </p>
                </div>
              </div>
            );

            return href ? (
              <Link
                key={n.id}
                href={href}
                onClick={() => {
                  if (n.read_at === null) void montra.markNotificationRead(n.id);
                }}
                className="block"
              >
                {inner}
              </Link>
            ) : (
              <div key={n.id}>{inner}</div>
            );
          })}
        </Card>
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Notifications />
      </RequireSession>
    </Providers>
  );
}
