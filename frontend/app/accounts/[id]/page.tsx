"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Account, Transaction, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { MoneyValue, TransactionRow } from "@/components/financial";
import { Button, Card, EmptyState, Skeleton, StatusChip } from "@/components/ui";

function AccountDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      montra.account(id),
      montra.transactions(`?account_id=${id}&limit=25`),
    ])
      .then(([a, t]) => {
        setAccount(a);
        setTransactions(t.data);
      })
      .catch(() => setAccount(null))
      .finally(() => setLoading(false));
  }, [id]);

  async function archive() {
    await montra.archiveAccount(id);
    router.push("/accounts");
    router.refresh();
  }

  if (loading) {
    return (
      <AppShell>
        <Skeleton className="h-40 w-full" />
      </AppShell>
    );
  }

  if (!account) {
    return (
      <AppShell>
        <EmptyState title="Account not found" message="It may have been removed." />
      </AppShell>
    );
  }

  const isLiability = account.account_nature === "LIABILITY";

  return (
    <AppShell>
      <PageHeader title={account.name} />
      <Card className="mb-6">
        <div className="flex items-center gap-2">
          <p className="text-sm text-content-secondary">
            {isLiability ? "Balance owed" : "Current balance"}
          </p>
          <StatusChip tone={isLiability ? "expense" : "neutral"}>
            {account.account_type.replace(/_/g, " ")}
          </StatusChip>
        </div>
        <p className="mt-2">
          <MoneyValue
            amount={account.balance}
            currency={account.currency}
            size="value-lg"
          />
        </p>
        {account.masked_identifier && (
          <p className="mt-1 text-xs text-content-muted">{account.masked_identifier}</p>
        )}
      </Card>

      <div className="mb-6 flex flex-wrap gap-3">
        <Button variant="secondary" onClick={() => router.push(`/add?account=${id}`)}>
          Add transaction
        </Button>
        <Button variant="secondary" onClick={() => router.push(`/transfer?from=${id}`)}>
          Transfer
        </Button>
        {account.can_edit && (
          <Button variant="destructive" onClick={archive}>
            Archive
          </Button>
        )}
      </div>

      <h2 className="mb-3 text-section">Activity</h2>
      {transactions.length === 0 ? (
        <EmptyState
          title="No activity yet"
          message="Transactions on this account will appear here."
        />
      ) : (
        <Card>
          {transactions.map((t) => (
            <TransactionRow key={t.id} transaction={t} />
          ))}
        </Card>
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <AccountDetail />
      </RequireSession>
    </Providers>
  );
}
