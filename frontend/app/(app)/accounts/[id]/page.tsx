"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Account, CardSummary, Transaction, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { MoneyValue, TransactionRow } from "@/components/financial";
import { CreditCardSummaryCard, ExpiryNotice } from "@/components/credit-card";
import { Button, Card, EmptyState, Skeleton, StatusChip } from "@/components/ui";

export default function AccountDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [summary, setSummary] = useState<CardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      montra.account(id),
      montra.transactions(`?account_id=${id}&limit=25`),
    ])
      .then(([a, t]) => {
        setAccount(a);
        setTransactions(t.data);
        if (a.account_type === "CREDIT_CARD") {
          montra.cardSummary(id).then(setSummary).catch(() => setSummary(null));
        }
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
      <>
        <Skeleton className="h-40 w-full" />
      </>
    );
  }

  if (!account) {
    return (
      <>
        <EmptyState title="Account not found" message="It may have been removed." />
      </>
    );
  }

  const isLiability = account.account_nature === "LIABILITY";
  const isCard = account.account_type === "CREDIT_CARD";
  const isPrepaid = account.account_type === "PREPAID_CARD";

  return (
    <>
      <PageHeader title={account.name} icon={isCard ? "creditCard" : "wallet"} />

      <div className="mb-6">
        {isCard && summary ? (
          <CreditCardSummaryCard summary={summary} />
        ) : (
          <Card>
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
            {account.expiry && (
              <div className="mt-4">
                <ExpiryNotice expiry={account.expiry} />
              </div>
            )}
          </Card>
        )}
      </div>

      <div className="mb-6 flex flex-wrap gap-3">
        {isCard && (
          <Button onClick={() => router.push(`/accounts/${id}/pay`)}>Make payment</Button>
        )}
        {isPrepaid && (
          <Button onClick={() => router.push(`/accounts/${id}/pay`)}>Top up</Button>
        )}
        {account.can_transact && (
          <>
            <Button variant="secondary" onClick={() => router.push(`/add?account=${id}`)}>
              Add transaction
            </Button>
            <Button variant="secondary" onClick={() => router.push(`/transfer?from=${id}`)}>
              Transfer
            </Button>
          </>
        )}
        {account.can_transact && (
          <Button variant="secondary" onClick={() => router.push(`/accounts/${id}/reconcile`)}>
            Reconcile
          </Button>
        )}
        {account.can_edit && (
          <Button variant="secondary" onClick={() => router.push(`/accounts/${id}/edit`)}>
            {isCard || isPrepaid ? "Card details" : "Account details"}
          </Button>
        )}
        {account.can_edit && (
          <Button variant="destructive" onClick={archive}>
            Archive
          </Button>
        )}
      </div>

      {!account.can_transact && (
        <p className="mb-6 rounded-control border border-line/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
          Shared with you to view. Only the owner can record transactions here.
        </p>
      )}

      <h2 className="mb-3 text-section">Activity</h2>
      {transactions.length === 0 ? (
        <EmptyState
          title="No activity yet"
          message="Transactions on this account will appear here."
        />
      ) : (
        <Card>
          {transactions.map((t) => (
            <TransactionRow key={t.id} transaction={t} showAccount={false} />
          ))}
        </Card>
      )}
    </>
  );
}
