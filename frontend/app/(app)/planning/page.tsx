"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { LoanPaymentDue, PlannedTransaction, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { formatDate, formatMoney, formatTime } from "@/lib/format";
import { Icon } from "@/components/icons";
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
  const isTransfer = planned.planned_type === "TRANSFER";

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
    <div className="border-b border-line/5 py-4 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-content-primary">
            {planned.description}
          </p>
          <p className="mt-0.5 truncate text-xs text-content-secondary">
            {formatTime(planned.expected_at)}
            {planned.account ? ` · ${planned.account.name}` : ""}
            {/* Both sides, since a transfer without its destination is half a
                sentence. */}
            {isTransfer && planned.destination_account
              ? ` → ${planned.destination_account.name}`
              : ""}
            {planned.source === "RECURRING" ? " · Recurring" : ""}
          </p>
        </div>
        <span
          className={`tabular shrink-0 text-sm font-semibold ${
            isTransfer
              ? "text-semantic-transfer"
              : isIncome
                ? "text-semantic-income"
                : "text-semantic-expense"
          }`}
        >
          {isTransfer ? "" : isIncome ? "+" : "−"}
          {formatMoney(planned.amount, planned.currency)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Link href={`/planning/${planned.id}/complete`} className="pressable">
          <span className="inline-flex min-h-[36px] items-center rounded-full bg-accent px-3 text-xs font-semibold text-background-primary">
            {isTransfer ? "Mark done" : isIncome ? "Mark received" : "Mark paid"}
          </span>
        </Link>
        <Link href={`/planning/${planned.id}/reschedule`} className="pressable pressable-tint rounded-full">
          <span className="inline-flex min-h-[36px] items-center rounded-full border border-line/10 px-3 text-xs text-content-secondary">
            Reschedule
          </span>
        </Link>
        {planned.source === "RECURRING" ? (
          <button
            disabled={busy}
            onClick={() => run(() => montra.skipPlanned(planned.id))}
            className="pressable pressable-tint min-h-[36px] rounded-full border border-line/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Skip this one
          </button>
        ) : (
          <button
            disabled={busy}
            onClick={() => run(() => montra.cancelPlanned(planned.id))}
            className="pressable pressable-tint min-h-[36px] rounded-full border border-line/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Cancel
          </button>
        )}
        {planned.status === "MISSED" && <StatusChip tone="expense">Missed</StatusChip>}
      </div>
    </div>
  );
}

function LoanPaymentRow({ due }: { due: LoanPaymentDue }) {
  const owed = due.direction === "PAYABLE";
  return (
    <div className="border-b border-line/5 py-4 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-line/5 text-content-secondary">
            <Icon name="handshake" size={18} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-content-primary">
              {due.description}
            </p>
            <p className="mt-0.5 truncate text-xs text-content-secondary">
              {formatDate(`${due.due_date}T00:00:00`)}
              {due.counterparty ? ` · ${due.counterparty}` : ""}
              {" · "}
              {owed ? "Loan payment" : "Repayment due to you"}
            </p>
          </div>
        </div>
        <span
          className={`tabular shrink-0 text-sm font-semibold ${
            owed ? "text-semantic-expense" : "text-semantic-income"
          }`}
        >
          {owed ? "−" : "+"}
          {formatMoney(due.amount, due.currency)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 pl-12">
        {/* Not completable inline: a loan payment splits across principal,
            interest and fees, and only the payer knows the split. */}
        <Link href={`/loans/${due.loan_id}/pay`}>
          <span className="pressable inline-flex min-h-[36px] items-center rounded-full bg-accent px-3 text-xs font-semibold text-background-primary">
            Record payment
          </span>
        </Link>
        <Link href={`/loans/${due.loan_id}`}>
          <span className="pressable pressable-tint inline-flex min-h-[36px] items-center rounded-full border border-line/10 px-3 text-xs text-content-secondary">
            View loan
          </span>
        </Link>
      </div>
    </div>
  );
}

export default function Planning() {
  const [rows, setRows] = useState<PlannedTransaction[] | null>(null);
  const [loanDues, setLoanDues] = useState<LoanPaymentDue[]>([]);

  const load = useCallback(() => {
    montra
      .planned()
      .then(setRows)
      .catch(() => setRows([]));
    // Loan payments are derived from each loan's own schedule, so they arrive
    // separately and are merged into the same buckets here.
    montra
      .upcomingLoanPayments()
      .then(setLoanDues)
      .catch(() => setLoanDues([]));
  }, []);

  useEffect(load, [load]);

  if (rows === null) {
    return (
      <>
        <PageHeader title="Upcoming"
        icon="calendar" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }

  const grouped = BUCKETS.map((b) => ({
    ...b,
    items: rows.filter((r) => r.bucket === b.key),
    loans: loanDues.filter((l) => l.bucket === b.key),
  })).filter((b) => b.items.length > 0 || b.loans.length > 0);

  // Transfers are excluded from both: money moving between your own accounts
  // is neither going out nor coming in.
  const outstanding =
    rows
      .filter((r) => r.planned_type === "EXPENSE")
      .reduce((sum, r) => sum + Number(r.amount), 0) +
    // Loan payments are money going out too.
    loanDues
      .filter((l) => l.direction === "PAYABLE")
      .reduce((sum, l) => sum + Number(l.amount), 0);
  const incoming =
    rows
      .filter((r) => r.planned_type === "INCOME")
      .reduce((sum, r) => sum + Number(r.amount), 0) +
    loanDues
      .filter((l) => l.direction === "RECEIVABLE")
      .reduce((sum, l) => sum + Number(l.amount), 0);
  const currency = rows[0]?.currency ?? loanDues[0]?.currency ?? "RWF";

  return (
    <>
      <PageHeader
        title="Upcoming"
        icon="calendar"
        action={
          <div className="flex items-center gap-3">
            {/* Hidden on the narrowest phones so the page title is not
                crushed; still reachable from More. */}
            <Link href="/planning/forecast" className="hidden text-xs text-accent sm:inline">
              Forecast
            </Link>
            <Link href="/planning/recurring" className="hidden text-xs text-accent sm:inline">
              Recurring
            </Link>
            <Link href="/planning/new">
              <Button>Add</Button>
            </Link>
          </div>
        }
      />

      {rows.length === 0 && loanDues.length === 0 ? (
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
            {/* Only shown when there is something to show: a list made only of
                transfers would otherwise report "going out 0". */}
            {outstanding > 0 && (
              <div>
                <span className="text-xs uppercase tracking-wide text-content-muted">
                  Going out
                </span>
                <p className="tabular mt-0.5 font-semibold text-semantic-expense">
                  {formatMoney(String(outstanding), currency)}
                </p>
              </div>
            )}
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
                  <StatusChip tone={group.tone}>
                    {group.items.length + group.loans.length}
                  </StatusChip>
                </div>
                <Card>
                  {group.items.map((p) => (
                    <PlannedRow key={p.id} planned={p} onChanged={load} />
                  ))}
                  {group.loans.map((l) => (
                    <LoanPaymentRow key={l.id} due={l} />
                  ))}
                </Card>
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}
