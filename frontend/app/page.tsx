"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Account, Transaction, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession, useSession } from "@/components/session";
import { AccountCard, MetricCard, TransactionRow } from "@/components/financial";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui";
import { ProfileAvatarLink } from "@/components/avatar";

/**
 * Home dashboard.
 *
 * Totals are computed from balances the API derives from the ledger; the client
 * never does financial arithmetic of its own beyond summing displayed values.
 */
function Home() {
  const { user } = useSession();
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [recent, setRecent] = useState<Transaction[]>([]);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    montra.accounts().then(setAccounts).catch(() => setAccounts([]));
    montra
      .transactions("?limit=5")
      .then((r) => setRecent(r.data))
      .catch(() => setRecent([]));
  }, []);

  const currency = user?.base_currency ?? "RWF";

  const totals = (accounts ?? []).reduce(
    (acc, a) => {
      const value = Number(a.balance);
      if (a.account_nature === "LIABILITY") acc.liabilities += value;
      else acc.assets += value;
      return acc;
    },
    { assets: 0, liabilities: 0 },
  );
  const netWorth = totals.assets - totals.liabilities;

  return (
    <AppShell>
      <PageHeader
        title={`Hello${user?.display_name ? `, ${user.display_name}` : ""}`}
        leading={user ? <ProfileAvatarLink user={user} /> : undefined}
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
            <p className="mt-1 text-xs text-content-muted">
              Assets minus what you owe, across {accounts.length} account
              {accounts.length === 1 ? "" : "s"}.
            </p>
          </Card>

          <div className="mb-6 grid grid-cols-2 gap-3">
            <MetricCard
              label="Assets"
              amount={String(totals.assets)}
              currency={currency}
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
              <div className="space-y-3">
                {accounts.slice(0, 3).map((a) => (
                  <AccountCard key={a.id} account={a} hidden={hidden} />
                ))}
              </div>
            )}
          </section>

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
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Home />
      </RequireSession>
    </Providers>
  );
}
