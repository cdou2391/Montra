"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Account, Forecast, Insight, Loan, Transaction, montra } from "@/lib/api";
import { ContextSwitch, useFinancialContext } from "@/components/context";
import { PageHeader } from "@/components/shell";
import { useSession } from "@/components/session";
import { AccountTile, MetricCard, TransactionRow } from "@/components/financial";
import { InsightList } from "@/components/insights";
import { ForecastChart } from "@/components/forecast-chart";
import { formatMoney } from "@/lib/format";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui";
import { ProfileAvatarLink } from "@/components/avatar";

/**
 * Home dashboard.
 *
 * Totals are computed from balances the API derives from the ledger; the client
 * never does financial arithmetic of its own beyond summing displayed values.
 */
export default function Home() {
  const { user } = useSession();
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [recent, setRecent] = useState<Transaction[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [hidden, setHidden] = useState(false);
  const { context, family } = useFinancialContext();

  useEffect(() => {
    montra.accounts(context).then(setAccounts).catch(() => setAccounts([]));
    // Loans are not accounts, but they are part of what you own and owe, so
    // net worth is wrong without them.
    if (context === "personal") montra.loans().then(setLoans).catch(() => setLoans([]));
    else setLoans([]);
    montra
      .forecast(context, "30d")
      .then(setForecast)
      .catch(() => setForecast(null));
    montra
      .insights(context)
      .then(setInsights)
      .catch(() => setInsights([]));
    montra
      .transactions(`?limit=5&context=${context}`)
      .then((r) => setRecent(r.data))
      .catch(() => setRecent([]));
  }, [context]);

  const currency = user?.base_currency ?? "RWF";

  // Sum the base-currency figure the API worked out, never the raw balance:
  // adding dollars to francs at 1:1 gives a wrong total, not a rough one. An
  // account with no rate is left out and named, so the gap is visible.
  const unconverted = new Set(
    (accounts ?? []).filter((a) => a.balance_in_base === null).map((a) => a.currency),
  );
  const totals = (accounts ?? []).reduce(
    (acc, a) => {
      if (a.balance_in_base === null) return acc;
      const value = Number(a.balance_in_base);
      if (a.account_nature === "LIABILITY") acc.liabilities += value;
      else acc.assets += value;
      return acc;
    },
    { assets: 0, liabilities: 0 },
  );

  // A receivable is something you own; a payable is something you owe.
  for (const loan of loans) {
    if (loan.status === "ARCHIVED") continue;
    const outstanding = Number(loan.outstanding_principal);
    if (loan.direction === "RECEIVABLE") totals.assets += outstanding;
    else totals.liabilities += outstanding;
  }

  const netWorth = totals.assets - totals.liabilities;

  return (
    <>
      {family && <ContextSwitch className="mb-5" />}

      <PageHeader
        title={
          context === "family"
            ? family?.name ?? "Household"
            : `Hello${user?.display_name ? `, ${user.display_name}` : ""}`
        }
        leading={
          context === "personal" && user ? <ProfileAvatarLink user={user} /> : undefined
        }
        action={
          <button
            onClick={() => setHidden((h) => !h)}
            className="shrink-0 text-xs text-content-secondary hover:text-content-primary"
          >
            {/* The avatar and bell share this row; the long label crushes the
                greeting on a narrow phone. */}
            <span className="sm:hidden">{hidden ? "Show" : "Hide"}</span>
            <span className="hidden sm:inline">
              {hidden ? "Show balances" : "Hide balances"}
            </span>
          </button>
        }
      />

      {accounts === null ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <>
          <Card className="mb-4">
            <p className="text-sm text-content-secondary">Net worth</p>
            <p className="mt-2">
              <span className="tabular text-value sm:text-value-lg">
                {hidden ? "••••••" : `${currency} ${netWorth.toLocaleString()}`}
              </span>
            </p>
            {unconverted.size > 0 && (
              <p className="mt-2 text-xs text-semantic-warning">
                Not counting your{" "}
                {[...unconverted].join(" and ")} balance
                {unconverted.size === 1 ? "" : "s"} —{" "}
                <Link href="/profile" className="pressable underline">
                  set an exchange rate
                </Link>
                .
              </p>
            )}
            <p className="mt-1 text-xs text-content-muted">
              Assets minus what you owe, across {accounts.length} account
              {accounts.length === 1 ? "" : "s"}
              {loans.length > 0
                ? ` and ${loans.length} loan${loans.length === 1 ? "" : "s"}`
                : ""}
              .
            </p>
          </Card>

          <div className="mb-6 grid grid-cols-2 gap-3">
            <MetricCard
              label="Assets"
              amount={String(totals.assets)}
              currency={currency}
              // Mirrors Owed beside it: neutral at zero, coloured once there
              // is something to say.
              tone={totals.assets > 0 ? "income" : "neutral"}
              hidden={hidden}
            />
            <MetricCard
              label="Owed"
              amount={String(totals.liabilities)}
              currency={currency}
              tone={totals.liabilities > 0 ? "expense" : "neutral"}
              hidden={hidden}
            />
          </div>

          <section className="mb-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-section">Accounts</h2>
              <Link href="/accounts" className="text-xs text-accent">
                View all
              </Link>
            </div>
            {accounts.length === 0 ? (
              <EmptyState
                title="No accounts yet"
                message="Add your first account to start tracking your position."
                action={
                  <Link href="/accounts/new">
                    <Button>Add account</Button>
                  </Link>
                }
              />
            ) : (
              /* Bleeds into the page padding so the row reads as scrollable
                 rather than as a list that happens to be cut off. scroll-pl
                 matches the padding: without it snapping aligns the first tile
                 to the container edge, eating the padding and leaving the row
                 visibly wider than every other section. */
              <div className="-mx-4 flex snap-x scroll-pl-4 gap-3 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:-mx-6 sm:scroll-pl-6 sm:px-6 [&::-webkit-scrollbar]:hidden">
                {accounts.map((a) => (
                  <AccountTile key={a.id} account={a} hidden={hidden} />
                ))}
              </div>
            )}
          </section>

          {forecast && forecast.points.length > 1 && (
            <section className="mb-6">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-section">Next 30 days</h2>
                <Link href="/planning/forecast" className="pressable text-xs text-accent">
                  Details
                </Link>
              </div>
              <Card>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  {/* Smaller than the net-worth headline above it: this is a
                      projection, and should not outshout the real figure. */}
                  <p className="tabular text-lg font-semibold text-content-primary">
                    {hidden
                      ? "••••••"
                      : formatMoney(forecast.projected_ending_balance, forecast.currency)}
                  </p>
                  {/* Direction is stated in words as well as by the arrow, so
                      it does not depend on reading the chart. */}
                  <p
                    className={`text-xs ${
                      Number(forecast.net_change) < 0
                        ? "text-semantic-expense"
                        : "text-semantic-income"
                    }`}
                  >
                    {Number(forecast.net_change) < 0 ? "Down " : "Up "}
                    {hidden
                      ? "•••"
                      : formatMoney(
                          String(Math.abs(Number(forecast.net_change))),
                          forecast.currency,
                        )}
                  </p>
                </div>
                <div className="mt-3">
                  <ForecastChart forecast={forecast} />
                </div>
              </Card>
            </section>
          )}

          {insights.length > 0 && (
            <section className="mb-6">
              <h2 className="mb-3 text-section">Worth knowing</h2>
              <InsightList insights={insights} />
            </section>
          )}

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-section">Recent activity</h2>
              <Link href="/transactions" className="text-xs text-accent">
                View all
              </Link>
            </div>
            {recent.length === 0 ? (
              <EmptyState
                title="Nothing recorded yet"
                message="Your income and expenses will appear here."
              />
            ) : (
              <Card>
                {recent.map((t) => (
                  <TransactionRow key={t.id} transaction={t} hidden={hidden} />
                ))}
              </Card>
            )}
          </section>
        </>
      )}
    </>
  );
}
