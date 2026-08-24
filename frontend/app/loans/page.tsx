"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Loan, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney } from "@/lib/format";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { LoanCard } from "@/components/loan-card";

/**
 * Loan list (UI/UX sections 50-51).
 *
 * Tabs use plain language — "I owe" and "Owed to me" — rather than PAYABLE and
 * RECEIVABLE, which are the database's words, not a person's.
 */

function Loans() {
  const [loans, setLoans] = useState<Loan[] | null>(null);
  const [tab, setTab] = useState<"PAYABLE" | "RECEIVABLE">("PAYABLE");

  const load = useCallback(() => {
    montra
      .loans()
      .then(setLoans)
      .catch(() => setLoans([]));
  }, []);
  useEffect(load, [load]);

  const shown = (loans ?? []).filter((l) => l.direction === tab);
  const currency = loans?.[0]?.currency ?? "RWF";

  const total = (direction: "PAYABLE" | "RECEIVABLE") =>
    (loans ?? [])
      .filter((l) => l.direction === direction && l.status === "ACTIVE")
      .reduce((sum, l) => sum + Number(l.outstanding_principal), 0);

  return (
    <AppShell>
      <PageHeader
        title="Loans"
        icon="handshake"
        action={
          <Link href="/loans/new">
            <Button>Add</Button>
          </Link>
        }
      />

      {loans === null ? (
        <Skeleton className="h-56 w-full" />
      ) : loans.length === 0 ? (
        <EmptyState
          title="No loans yet"
          message="Track what you owe and what people owe you, so your net worth tells the whole story."
          action={
            <Link href="/loans/new">
              <Button>Add a loan</Button>
            </Link>
          }
        />
      ) : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-2 rounded-control bg-background-secondary p-1">
            {([
              ["PAYABLE", "I owe"],
              ["RECEIVABLE", "Owed to me"],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTab(value)}
                aria-pressed={tab === value}
                className={`pressable min-h-[44px] rounded-[10px] text-sm font-semibold transition ${
                  tab === value
                    ? value === "PAYABLE"
                      ? "bg-semantic-expense/15 text-semantic-expense"
                      : "bg-semantic-income/15 text-semantic-income"
                    : "text-content-secondary"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mb-5">
            <span className="text-xs uppercase tracking-wide text-content-muted">
              {tab === "PAYABLE" ? "Total you owe" : "Total owed to you"}
            </span>
            <p
              className={`tabular mt-0.5 text-value ${
                tab === "PAYABLE" ? "text-semantic-expense" : "text-semantic-income"
              }`}
            >
              {formatMoney(String(total(tab)), currency)}
            </p>
          </div>

          {shown.length === 0 ? (
            <EmptyState
              title={tab === "PAYABLE" ? "Nothing owed" : "Nobody owes you"}
              message={
                tab === "PAYABLE"
                  ? "You have no loans to repay."
                  : "You have not lent anything out."
              }
            />
          ) : (
            <div className="space-y-3">
              {shown.map((loan) => (
                <LoanCard key={loan.id} loan={loan} />
              ))}
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Loans />
      </RequireSession>
    </Providers>
  );
}
