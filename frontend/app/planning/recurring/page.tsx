"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { RecurringRule, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney } from "@/lib/format";
import { Button, Card, EmptyState, Skeleton, StatusChip } from "@/components/ui";

const CADENCE: Record<string, string> = {
  DAILY: "day",
  WEEKLY: "week",
  MONTHLY: "month",
  QUARTERLY: "quarter",
  YEARLY: "year",
};

function describe(rule: RecurringRule): string {
  const unit = CADENCE[rule.frequency] ?? rule.frequency.toLowerCase();
  return rule.interval_value === 1
    ? `Every ${unit}`
    : `Every ${rule.interval_value} ${unit}s`;
}

function RuleCard({ rule, onChanged }: { rule: RecurringRule; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const isIncome = rule.planned_type === "INCOME";

  async function act(action: "pause" | "resume" | "end") {
    setBusy(true);
    try {
      await montra.ruleAction(rule.id, action);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate font-medium text-content-primary">{rule.name}</p>
          <p className="mt-1 text-xs text-content-secondary">
            {describe(rule)}
            {rule.next_occurrence_date ? ` · next ${rule.next_occurrence_date}` : ""}
          </p>
        </div>
        <span
          className={`tabular shrink-0 text-sm font-semibold ${
            isIncome ? "text-semantic-income" : "text-semantic-expense"
          }`}
        >
          {isIncome ? "+" : "−"}
          {formatMoney(rule.amount, rule.currency)}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {rule.status !== "ACTIVE" && (
          <StatusChip tone={rule.status === "ENDED" ? "expense" : "warning"}>
            {rule.status === "ENDED" ? "Ended" : "Paused"}
          </StatusChip>
        )}
        {rule.status === "ACTIVE" && (
          <button
            disabled={busy}
            onClick={() => act("pause")}
            className="min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Pause
          </button>
        )}
        {rule.status === "PAUSED" && (
          <button
            disabled={busy}
            onClick={() => act("resume")}
            className="min-h-[36px] rounded-full bg-accent px-3 text-xs font-semibold text-background-primary disabled:opacity-40"
          >
            Resume
          </button>
        )}
        {rule.status !== "ENDED" && (
          <button
            disabled={busy}
            onClick={() => act("end")}
            className="min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-semantic-expense disabled:opacity-40"
          >
            End series
          </button>
        )}
      </div>
    </Card>
  );
}

function Recurring() {
  const [rules, setRules] = useState<RecurringRule[] | null>(null);

  const load = useCallback(() => {
    montra
      .recurringRules()
      .then(setRules)
      .catch(() => setRules([]));
  }, []);
  useEffect(load, [load]);

  return (
    <AppShell>
      <PageHeader
        title="Recurring"
        icon="repeat"
        action={
          <div className="flex items-center gap-3">
            <Link href="/planning" className="hidden text-xs text-accent sm:inline">
              Upcoming
            </Link>
            <Link href="/planning/recurring/new">
              <Button>Add</Button>
            </Link>
          </div>
        }
      />

      {rules === null ? (
        <Skeleton className="h-48 w-full" />
      ) : rules.length === 0 ? (
        <EmptyState
          title="No recurring items"
          message="Set up rent, subscriptions or a salary once and Montra will keep the upcoming list filled in."
          action={
            <Link href="/planning/recurring/new">
              <Button>Add recurring</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-3">
          {rules.map((r) => (
            <RuleCard key={r.id} rule={r} onChanged={load} />
          ))}
        </div>
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Recurring />
      </RequireSession>
    </Providers>
  );
}
