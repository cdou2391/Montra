"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Loan, RecurringRule, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { formatMoney } from "@/lib/format";
import { Icon } from "@/components/icons";
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
  const isTransfer = rule.planned_type === "TRANSFER";

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
            {isTransfer ? "Transfer · " : ""}
            {describe(rule)}
            {rule.next_occurrence_date ? ` · next ${rule.next_occurrence_date}` : ""}
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
            className="pressable pressable-tint min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Pause
          </button>
        )}
        {rule.status === "PAUSED" && (
          <button
            disabled={busy}
            onClick={() => act("resume")}
            className="pressable min-h-[36px] rounded-full bg-accent px-3 text-xs font-semibold text-background-primary disabled:opacity-40"
          >
            Resume
          </button>
        )}
        {rule.status !== "ENDED" && (
          <button
            disabled={busy}
            onClick={() => act("end")}
            className="pressable pressable-tint min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-semantic-expense disabled:opacity-40"
          >
            End series
          </button>
        )}
      </div>
    </Card>
  );
}

/**
 * A loan with a payment schedule is a recurring commitment too, but it is not
 * a RecurringRule: the loan owns its own schedule. Shown here for what it is,
 * managed from the loan itself.
 */
function ScheduledLoanCard({ loan }: { loan: Loan }) {
  const owed = loan.direction === "PAYABLE";
  const cadence = loan.payment_frequency
    ? `Every ${(CADENCE[loan.payment_frequency] ?? loan.payment_frequency).toLowerCase()}`
    : "One payment";

  return (
    <Link href={`/loans/${loan.id}`} className="pressable pressable-surface block">
      <Card className="transition-colors hover:bg-surface-elevated">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 text-content-secondary">
              <Icon name="handshake" size={18} />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium text-content-primary">{loan.name}</p>
              <p className="mt-1 truncate text-xs text-content-secondary">
                {cadence}
                {loan.next_payment_date ? ` · next ${loan.next_payment_date}` : ""}
              </p>
            </div>
          </div>
          <span
            className={`tabular shrink-0 text-sm font-semibold ${
              owed ? "text-semantic-expense" : "text-semantic-income"
            }`}
          >
            {owed ? "−" : "+"}
            {formatMoney(loan.expected_payment_amount ?? "0", loan.currency)}
          </span>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <StatusChip tone={owed ? "expense" : "income"}>Loan</StatusChip>
          <span className="text-xs text-content-muted">
            {formatMoney(loan.outstanding_principal, loan.currency)} outstanding
          </span>
        </div>
      </Card>
    </Link>
  );
}

export default function Recurring() {
  const [rules, setRules] = useState<RecurringRule[] | null>(null);
  const [loans, setLoans] = useState<Loan[]>([]);

  const load = useCallback(() => {
    montra
      .recurringRules()
      .then(setRules)
      .catch(() => setRules([]));
    montra
      .loans()
      .then((all) =>
        setLoans(
          all.filter(
            (l) => l.status === "ACTIVE" && l.next_payment_date && l.expected_payment_amount,
          ),
        ),
      )
      .catch(() => setLoans([]));
  }, []);
  useEffect(load, [load]);

  return (
    <>
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
      ) : rules.length === 0 && loans.length === 0 ? (
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
        <div className="space-y-6">
          {rules.length > 0 && (
            <div className="space-y-3">
              {rules.map((r) => (
                <RuleCard key={r.id} rule={r} onChanged={load} />
              ))}
            </div>
          )}

          {loans.length > 0 && (
            <section>
              <h2 className="mb-3 text-section text-content-secondary">Loan payments</h2>
              <div className="space-y-3">
                {loans.map((l) => (
                  <ScheduledLoanCard key={l.id} loan={l} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </>
  );
}
