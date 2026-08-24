"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PlannedTransaction, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney, formatTime } from "@/lib/format";
import { Button, Card, EmptyState, Skeleton, StatusChip } from "@/components/ui";

/**
 * Upcoming screen (Implementation Plan Phase 11).
 *
 * Grouped Overdue / Today / Tomorrow / This Week / Later. Nothing here has
 * touched a balance yet — completing an item is what posts it.
 */

const BUCKETS = [
  { key: "OVERDUE", label: "Overdue", tone: "expense" as const },
  { key: "TODAY", label: "Today", tone: "warning" as const },
  { key: "TOMORROW", label: "Tomorrow", tone: "neutral" as const },
  { key: "THIS_WEEK", label: "This week", tone: "neutral" as const },
  { key: "LATER", label: "Later", tone: "neutral" as const },
];

function PlannedRow({
  planned,
  onChanged,
}: {
  planned: PlannedTransaction;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const isIncome = planned.planned_type === "INCOME";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-b border-white/5 py-4 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-content-primary">
            {planned.description}
          </p>
          <p className="mt-0.5 truncate text-xs text-content-secondary">
            {formatTime(planned.expected_at)}
            {planned.account ? ` · ${planned.account.name}` : ""}
            {planned.source === "RECURRING" ? " · Recurring" : ""}
          </p>
        </div>
        <span
          className={`tabular shrink-0 text-sm font-semibold ${
            isIncome ? "text-semantic-income" : "text-semantic-expense"
          }`}
        >
          {isIncome ? "+" : "−"}
          {formatMoney(planned.amount, planned.currency)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Link href={`/planning/${planned.id}/complete`}>
          <span className="inline-flex min-h-[36px] items-center rounded-full bg-accent px-3 text-xs font-semibold text-background-primary">
            {isIncome ? "Mark received" : "Mark paid"}
          </span>
        </Link>
        <Link href={`/planning/${planned.id}/reschedule`}>
          <span className="inline-flex min-h-[36px] items-center rounded-full border border-white/10 px-3 text-xs text-content-secondary">
            Reschedule
          </span>
        </Link>
        {planned.source === "RECURRING" ? (
          <button
            disabled={busy}
            onClick={() => run(() => montra.skipPlanned(planned.id))}
            className="min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Skip this one
          </button>
        ) : (
          <button
            disabled={busy}
            onClick={() => run(() => montra.cancelPlanned(planned.id))}
            className="min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Cancel
          </button>
        )}
        {planned.status === "MISSED" && <StatusChip tone="expense">Missed</StatusChip>}
      </div>
    </div>
  );
}

function Planning() {
  const [rows, setRows] = useState<PlannedTransaction[] | null>(null);

  const load = useCallback(() => {
    montra
      .planned()
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  useEffect(load, [load]);

  if (rows === null) {
    return (
      <AppShell>
        <PageHeader title="Upcoming" />
        <Skeleton className="h-64 w-full" />
      </AppShell>
    );
  }

  const grouped = BUCKETS.map((b) => ({
    ...b,
    items: rows.filter((r) => r.bucket === b.key),
  })).filter((b) => b.items.length > 0);

  const outstanding = rows
    .filter((r) => r.planned_type === "EXPENSE")
    .reduce((sum, r) => sum + Number(r.amount), 0);
  const incoming = rows
    .filter((r) => r.planned_type === "INCOME")
    .reduce((sum, r) => sum + Number(r.amount), 0);
  const currency = rows[0]?.currency ?? "RWF";

  return (
    <AppShell>
      <PageHeader
        title="Upcoming"
        action={
          <div className="flex items-center gap-3">
            <Link href="/planning/recurring" className="text-xs text-accent">
              Recurring
            </Link>
            <Link href="/planning/new">
              <Button>Add</Button>
            </Link>
          </div>
        }
      />

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing scheduled"
          message="Add a bill or expected income and it will show up here before it lands."
          action={
            <Link href="/planning/new">
              <Button>Add upcoming</Button>
            </Link>
          }
        />
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-baseline gap-x-8 gap-y-2">
            <div>
              <span className="text-xs uppercase tracking-wide text-content-muted">
                Going out
              </span>
              <p className="tabular mt-0.5 font-semibold text-semantic-expense">
                {formatMoney(String(outstanding), currency)}
              </p>
            </div>
            {incoming > 0 && (
              <div>
                <span className="text-xs uppercase tracking-wide text-content-muted">
                  Coming in
                </span>
                <p className="tabular mt-0.5 font-semibold text-semantic-income">
                  {formatMoney(String(incoming), currency)}
                </p>
              </div>
            )}
          </div>

          <div className="space-y-6">
            {grouped.map((group) => (
              <section key={group.key}>
                <div className="mb-2 flex items-center gap-2">
                  <h2 className="text-section">{group.label}</h2>
                  <StatusChip tone={group.tone}>{group.items.length}</StatusChip>
                </div>
                <Card>
                  {group.items.map((p) => (
                    <PlannedRow key={p.id} planned={p} onChanged={load} />
                  ))}
                </Card>
              </section>
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Planning />
      </RequireSession>
    </Providers>
  );
}
