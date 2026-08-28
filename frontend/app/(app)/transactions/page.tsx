"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Account, Category, Transaction, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { ContextSwitch, useFinancialContext } from "@/components/context";
import { TransactionRow } from "@/components/financial";
import { TransactionTable } from "@/components/transaction-table";
import { FilterControls, FilterSheet, Filters, EMPTY_FILTERS, activeCount } from "@/components/filters";
import { Icon } from "@/components/icons";
import { Button, Card, EmptyState, Input } from "@/components/ui";
import { SkeletonRows } from "@/components/skeletons";

/**
 * Transactions (Implementation Plan Phase 26).
 *
 * The same filter state drives both layouts: a bottom sheet on a phone, an
 * inline row and a table on a wide screen. Filtering happens on the server, so
 * a narrowed view is the whole history narrowed, not just the page in hand.
 */
function Transactions() {
  const params = useSearchParams();
  const { context, family } = useFinancialContext();

  const [rows, setRows] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Arriving from an account's "View all" pre-selects that account.
  const [filters, setFilters] = useState<Filters>({
    ...EMPTY_FILTERS,
    account_id: params.get("account") ?? "",
  });
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    montra.accounts(context).then(setAccounts).catch(() => setAccounts([]));
  }, [context]);

  useEffect(() => {
    montra.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  // A request per keystroke would be one per letter of "supermarket".
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const query = useCallback(
    (nextCursor?: string) => {
      const q = new URLSearchParams({ limit: "25", context });
      const send: Record<string, string> = { ...filters, search: debouncedSearch };
      for (const [key, value] of Object.entries(send)) {
        if (value) q.set(key, value);
      }
      if (nextCursor) q.set("cursor", nextCursor);
      return `?${q.toString()}`;
    },
    [filters, debouncedSearch, context],
  );

  useEffect(() => {
    setLoading(true);
    montra
      .transactions(query())
      .then((r) => {
        setRows(r.data);
        setCursor(r.pagination.next_cursor);
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [query]);

  async function loadMore() {
    if (!cursor) return;
    const r = await montra.transactions(query(cursor));
    setRows((existing) => [...existing, ...r.data]);
    setCursor(r.pagination.next_cursor);
  }

  const count = useMemo(() => activeCount(filters), [filters]);
  // The search box is not in the sheet, so it stays out of the badge — but it
  // narrows the view just as much, so clearing has to reach it.
  const narrowed = count > 0 || debouncedSearch !== "";

  function clearEverything() {
    setFilters(EMPTY_FILTERS);
    setSearch("");
  }

  return (
    <>
      {family && <ContextSwitch className="mb-5" />}

      <PageHeader
        title="Transactions"
        icon="list"
        action={
          // "Transactions" is a longer title than the row used to carry, and
          // the title must not be the thing that gives way. The action gives
          // way instead, down to its glyph on a narrow phone.
          <Link href="/add" aria-label="Add transaction">
            {/* px-5 is the standard button gutter; at 320px those few pixels
                are the difference between a whole title and a truncated one.
                Marked important because Tailwind orders px-5 after px-3.5 in
                the sheet, so a plain override loses. */}
            <Button className="!px-3.5 sm:!px-5">
              <span aria-hidden className="sm:hidden">
                +
              </span>
              <span className="hidden sm:inline">Add</span>
            </Button>
          </Link>
        }
      />

      <div className="mb-4 flex gap-3">
        <Input
          type="search"
          placeholder="Search description or merchant"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1"
        />
        {/* The sheet is the phone's filter surface; wide screens get the
            controls laid out below instead. */}
        <button
          onClick={() => setSheetOpen(true)}
          className="pressable pressable-surface flex min-h-[44px] shrink-0 items-center gap-2 rounded-control border border-line/10 px-3 text-sm text-content-secondary lg:hidden"
        >
          <Icon name="filter" size={16} />
          Filters
          {count > 0 && (
            <span className="rounded-full bg-accent px-1.5 text-xs font-semibold text-background-primary">
              {count}
            </span>
          )}
        </button>
      </div>

      <div className="mb-5 hidden lg:block">
        <FilterControls
          filters={filters}
          onChange={setFilters}
          accounts={accounts}
          categories={categories}
          members={context === "family" ? (family?.members ?? []) : []}
          layout="inline"
        />
      </div>

      {narrowed && (
        <div className="mb-4 flex items-center justify-between text-xs text-content-secondary">
          <span>
            {count > 0 && `${count} filter${count === 1 ? "" : "s"} applied`}
            {count > 0 && debouncedSearch && ", "}
            {debouncedSearch && `searching “${debouncedSearch}”`}
          </span>
          <button onClick={clearEverything} className="pressable text-accent">
            Clear all
          </button>
        </div>
      )}

      {loading ? (
        <SkeletonRows rows={6} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing to show"
          message={
            narrowed
              ? "No transactions match these filters."
              : "Your income and expenses will appear here."
          }
          action={
            narrowed ? (
              <Button variant="secondary" onClick={clearEverything}>
                Clear filters
              </Button>
            ) : (
              <Link href="/add">
                <Button>Add transaction</Button>
              </Link>
            )
          }
        />
      ) : (
        <>
          {/* Same rows, two readings: a list where space is scarce, a table
              where there is room to scan columns. */}
          <div className="lg:hidden">
            <Card>
              {rows.map((t) => (
                <TransactionRow key={t.id} transaction={t} />
              ))}
            </Card>
          </div>
          <div className="hidden lg:block">
            <TransactionTable transactions={rows} />
          </div>

          {cursor && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={loadMore}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}

      <FilterSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        filters={filters}
        onChange={setFilters}
        accounts={accounts}
        categories={categories}
        members={context === "family" ? (family?.members ?? []) : []}
      />
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
