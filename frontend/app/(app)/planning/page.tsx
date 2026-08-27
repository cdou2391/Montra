"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { LoanPaymentDue, PlannedTransaction, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { MetricCard } from "@/components/financial";
import { formatDayShort, formatMoney, formatTime } from "@/lib/format";
import { Button, Card, EmptyState, Skeleton, StatusChip } from "@/components/ui";

/**
 * Upcoming screen.
 *
 * Grouped Overdue / Today / Tomorrow / This Week / Later. Nothing here has
 * touched a balance yet — completing an item is what posts it.
 */

// `dated` marks the groups that span more than one day, where a row has to
// carry its own date. Under "Today" and "Tomorrow" the heading already says
// which day it is, and repeating it on every row is noise.
const BUCKETS = [
  { key: "OVERDUE", label: "Overdue", tone: "expense" as const, dated: true },
  { key: "TODAY", label: "Today", tone: "warning" as const, dated: false },
  { key: "TOMORROW", label: "Tomorrow", tone: "neutral" as const, dated: false },
  { key: "THIS_WEEK", label: "This week", tone: "neutral" as const, dated: true },
  { key: "LATER", label: "Later", tone: "neutral" as const, dated: true },
];

function PlannedRow({
  planned,
  showDate,
  onChanged,
}: {
  planned: PlannedTransaction;
  showDate: boolean;
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
          {/* Wraps rather than truncating: with a date in front, one line is
              no longer enough for a transfer's two account names, and the row
              has the vertical space to spare. */}
          <p className="mt-0.5 text-xs text-content-secondary">
            {/* Date first — which day it falls on is what tells two otherwise
                identical recurring rows apart. */}
            {showDate ? `${formatDayShort(planned.expected_at)}, ` : ""}
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

/** One row of a bucket, whichever endpoint it came from. */
type Entry =
  | { kind: "planned"; at: number; planned: PlannedTransaction }
  | { kind: "loan"; at: number; due: LoanPaymentDue };

function LoanPaymentRow({ due }: { due: LoanPaymentDue }) {
  const owed = due.direction === "PAYABLE";
  return (
    <div className="border-b border-line/5 py-4 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-content-primary">
            {due.description}
          </p>
          <p className="mt-0.5 text-xs text-content-secondary">
            {/* Same date format as the planned rows beside it. A loan is due
                on a day rather than at a time, so this stays put even under
                Today, where it is the row's only temporal anchor. */}
            {formatDayShort(`${due.due_date}T00:00:00`)}
            {due.counterparty ? ` · ${due.counterparty}` : ""}
            {" · "}
            {owed ? "Loan payment" : "Repayment due to you"}
          </p>
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

      <div className="mt-3 flex flex-wrap items-center gap-2">
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

  // Planned items and loan payments come from different endpoints, and a
  // bucket has to interleave them by date. Rendered as two blocks they were
  // ordered by source instead: every loan sat below every planned item, so a
  // 28 September instalment came after a 26 October transfer.
  //
  // Sorted on the value each row actually displays — a loan is due on a day
  // rather than at a time, so it takes local midnight and leads that day.
  const entriesIn = (key: string): Entry[] =>
    [
      ...rows
        .filter((r) => r.bucket === key)
        .map((planned): Entry => ({
          kind: "planned",
          at: new Date(planned.expected_at).getTime(),
          planned,
        })),
      ...loanDues
        .filter((l) => l.bucket === key)
        .map((due): Entry => ({
          kind: "loan",
          at: new Date(`${due.due_date}T00:00:00`).getTime(),
          due,
        })),
    ].sort((a, b) => a.at - b.at);

  const grouped = BUCKETS.map((b) => ({ ...b, entries: entriesIn(b.key) })).filter(
    (b) => b.entries.length > 0,
  );

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
          {/* The pair is shown or hidden together, so the two cards are always
              even. Suppressed entirely when both are zero: a list made only of
              transfers has nothing going out or coming in, and a row of noughts
              says less than no row at all. */}
          {(outstanding > 0 || incoming > 0) && (
            <div className="mb-6 grid grid-cols-2 gap-3">
              <MetricCard
                label="Going out"
                amount={String(outstanding)}
                currency={currency}
                // As on Home: neutral at zero, coloured once there is
                // something to say.
                tone={outstanding > 0 ? "expense" : "neutral"}
              />
              <MetricCard
                label="Coming in"
                amount={String(incoming)}
                currency={currency}
                tone={incoming > 0 ? "income" : "neutral"}
              />
            </div>
          )}

          <div className="space-y-6">
            {grouped.map((group) => (
              <section key={group.key}>
                <div className="mb-2 flex items-center gap-2">
                  <h2 className="text-section">{group.label}</h2>
                  <StatusChip tone={group.tone}>{group.entries.length}</StatusChip>
                </div>
                <Card>
                  {group.entries.map((entry) =>
                    entry.kind === "planned" ? (
                      <PlannedRow
                        key={entry.planned.id}
                        planned={entry.planned}
                        showDate={group.dated}
                        onChanged={load}
                      />
                    ) : (
                      <LoanPaymentRow key={entry.due.id} due={entry.due} />
                    ),
                  )}
                </Card>
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}
