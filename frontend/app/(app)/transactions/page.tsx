"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Account, Transaction, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { TransactionRow } from "@/components/financial";
import { Button, Card, EmptyState, Input, Select, Skeleton } from "@/components/ui";

function Transactions() {
  const params = useSearchParams();
  const [rows, setRows] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Arriving from an account's "View all" pre-selects that account.
  const [filters, setFilters] = useState({
    account_id: params.get("account") ?? "",
    type: "",
    search: "",
  });

  useEffect(() => {
    montra.accounts().then(setAccounts);
  }, []);

  const query = useCallback(
    (nextCursor?: string) => {
      const params = new URLSearchParams({ limit: "25" });
      if (filters.account_id) params.set("account_id", filters.account_id);
      if (filters.type) params.set("type", filters.type);
      if (filters.search) params.set("search", filters.search);
      if (nextCursor) params.set("cursor", nextCursor);
      return `?${params.toString()}`;
    },
    [filters],
  );

  useEffect(() => {
    setLoading(true);
    montra
      .transactions(query())
      .then((r) => {
        setRows(r.data);
        setCursor(r.pagination.next_cursor);
      })
      .finally(() => setLoading(false));
  }, [query]);

  async function loadMore() {
    if (!cursor) return;
    const r = await montra.transactions(query(cursor));
    setRows((existing) => [...existing, ...r.data]);
    setCursor(r.pagination.next_cursor);
  }

  return (
    <>
      <PageHeader
        title="Activity"
        icon="list"
        action={
          <Link href="/add">
            <Button>Add</Button>
          </Link>
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Input
          placeholder="Search"
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
        />
        <Select
          value={filters.account_id}
          onChange={(e) => setFilters((f) => ({ ...f, account_id: e.target.value }))}
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select
          value={filters.type}
          onChange={(e) => setFilters((f) => ({ ...f, type: e.target.value }))}
        >
          <option value="">All types</option>
          <option value="INCOME">Income</option>
          <option value="EXPENSE">Expense</option>
          <option value="TRANSFER">Transfer</option>
          <option value="ADJUSTMENT">Adjustment</option>
        </Select>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing to show"
          message="No transactions match these filters yet."
          action={
            <Link href="/add">
              <Button>Add transaction</Button>
            </Link>
          }
        />
      ) : (
        <>
          <Card>
            {rows.map((t) => (
              <TransactionRow key={t.id} transaction={t} />
            ))}
          </Card>
          {cursor && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={loadMore}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Transactions />
    </Suspense>
  );
}
