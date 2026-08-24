"use client";

/**
 * Loan card (UI/UX section 51): outstanding, progress, and the next payment.
 */

import Link from "next/link";

import { Loan } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { Card, StatusChip } from "@/components/ui";

function ProgressBar({ percent }: { percent: number }) {
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Principal repaid"
      className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/8"
    >
      <div
        className="h-full rounded-full bg-accent transition-all"
        style={{ width: `${Math.min(Math.max(percent, 0), 100)}%` }}
      />
    </div>
  );
}

export function LoanCard({ loan }: { loan: Loan }) {
  const percent = loan.percent_paid ? Number(loan.percent_paid) : 0;
  const owed = loan.direction === "PAYABLE";

  return (
    <Link href={`/loans/${loan.id}`} className="pressable pressable-surface block">
      <Card className="transition-colors hover:bg-surface-elevated">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate font-medium text-content-primary">{loan.name}</p>
            {loan.counterparty && (
              <p className="mt-0.5 truncate text-xs text-content-secondary">
                {loan.counterparty}
              </p>
            )}
          </div>
          {loan.status !== "ACTIVE" && (
            <StatusChip tone={loan.status === "SETTLED" ? "income" : "neutral"}>
              {loan.status === "SETTLED" ? "Settled" : "Archived"}
            </StatusChip>
          )}
        </div>

        <p className="mt-3 text-xs uppercase tracking-wide text-content-muted">
          {owed ? "Outstanding" : "Still owed to you"}
        </p>
        <p
          className={`tabular mt-1 text-xl font-bold ${
            owed ? "text-content-primary" : "text-semantic-income"
          }`}
        >
          {formatMoney(loan.outstanding_principal, loan.currency)}
        </p>

        <ProgressBar percent={percent} />
        <p className="mt-1.5 text-xs text-content-muted">
          {loan.percent_paid ?? "0"}% paid ·{" "}
          {formatMoney(loan.original_principal, loan.currency)} originally
        </p>

        {loan.next_payment_date && loan.expected_payment_amount && loan.status === "ACTIVE" && (
          <p className="mt-3 border-t border-white/5 pt-3 text-xs text-content-secondary">
            Next {formatMoney(loan.expected_payment_amount, loan.currency)} ·{" "}
            {loan.next_payment_date}
          </p>
        )}
      </Card>
    </Link>
  );
}
