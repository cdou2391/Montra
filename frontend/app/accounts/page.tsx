"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Account, Transaction, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { MoneyValue, TransactionRow } from "@/components/financial";
import { AccountPanel } from "@/components/account-panel";
import { Icon } from "@/components/icons";
import {
  CarouselChevron,
  CarouselPosition,
  CarouselSlide,
  CarouselTrack,
  useCarousel,
} from "@/components/carousel";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui";

const RECENT_LIMIT = 6;

function Accounts() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [hidden, setHidden] = useState(false);

  // Recent activity is cached per account so swiping back and forth does not
  // refetch what we already have.
  const [activity, setActivity] = useState<Record<string, Transaction[]>>({});
  const [loadingActivity, setLoadingActivity] = useState(false);
  const inFlight = useRef<Set<string>>(new Set());

  const { trackRef, index, onScroll, select } = useCarousel(accounts?.length ?? 0);
  const active = accounts?.[index];

  const loadAccounts = useCallback(() => {
    montra.accounts().then(setAccounts).catch(() => setAccounts([]));
  }, []);

  useEffect(loadAccounts, [loadAccounts]);

  useEffect(() => {
    if (!active || activity[active.id] || inFlight.current.has(active.id)) return;
    inFlight.current.add(active.id);
    setLoadingActivity(true);
    montra
      .transactions(`?account_id=${active.id}&limit=${RECENT_LIMIT}`)
      .then((r) => setActivity((prev) => ({ ...prev, [active.id]: r.data })))
      .catch(() => setActivity((prev) => ({ ...prev, [active.id]: [] })))
      .finally(() => {
        inFlight.current.delete(active.id);
        setLoadingActivity(false);
      });
  }, [active, activity]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!accounts) return;
      if (e.key === "ArrowRight" && index < accounts.length - 1) {
        e.preventDefault();
        select(index + 1);
      }
      if (e.key === "ArrowLeft" && index > 0) {
        e.preventDefault();
        select(index - 1);
      }
    },
    [accounts, index, select],
  );

  if (accounts === null) {
    return (
      <AppShell>
        <PageHeader title="Accounts"
        icon="wallet" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="mt-6 h-64 w-full" />
      </AppShell>
    );
  }

  if (accounts.length === 0) {
    return (
      <AppShell>
        <PageHeader title="Accounts"
        icon="wallet" />
        <EmptyState
          title="No accounts yet"
          message="Add a bank account, cash, mobile money or a card to get started."
          action={
            <Link href="/accounts/new">
              <Button>Add account</Button>
            </Link>
          }
        />
      </AppShell>
    );
  }

  const totals = accounts.reduce(
    (acc, a) => {
      const value = Number(a.balance);
      if (a.account_nature === "LIABILITY") acc.owed += value;
      else acc.available += value;
      return acc;
    },
    { available: 0, owed: 0 },
  );

  const rows = active ? activity[active.id] : undefined;

  return (
    <AppShell>
      <PageHeader
        title="Accounts"
        icon="wallet"
        action={
          <Link href="/accounts/new">
            <Button>
              <span className="sm:hidden">Add</span>
              <span className="hidden sm:inline">New account</span>
            </Button>
          </Link>
        }
      />

      {/* Totals across every account, so swiping never loses the whole picture. */}
      <div className="mb-5 flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <button
          onClick={() => setHidden((h) => !h)}
          className="order-last ml-auto text-xs text-content-secondary hover:text-content-primary"
        >
          {hidden ? "Show balances" : "Hide balances"}
        </button>
        <div>
          <span className="text-xs uppercase tracking-wide text-content-muted">
            Total available
          </span>
          <p className="mt-0.5">
            <MoneyValue
              amount={String(totals.available)}
              currency={accounts[0].currency}
              hidden={hidden}
            />
          </p>
        </div>
        {totals.owed > 0 && (
          <div>
            <span className="text-xs uppercase tracking-wide text-content-muted">Owed</span>
            <p className="mt-0.5">
              <MoneyValue
                amount={String(totals.owed)}
                currency={accounts[0].currency}
                tone="expense"
                hidden={hidden}
              />
            </p>
          </div>
        )}
      </div>

      {/* ---------------------------------------------- mobile + tablet: carousel */}
      <div className="lg:hidden">
        {/* Chevrons flank the card and are vertically centred against it. */}
        <div className="flex items-center gap-0.5 sm:gap-1">
          {accounts.length > 1 && (
            <CarouselChevron
              direction="left"
              disabled={index === 0}
              onClick={() => select(index - 1)}
              label="Previous account"
            />
          )}

          <CarouselTrack
            trackRef={trackRef}
            onScroll={onScroll}
            onKeyDown={onKeyDown}
            label="Your accounts"
          >
            {accounts.map((account, i) => (
              <CarouselSlide
                key={account.id}
                label={account.name}
                position={i + 1}
                total={accounts.length}
              >
                <AccountPanel
                account={account}
                hidden={hidden}
                onFavoriteChanged={loadAccounts}
              />
              </CarouselSlide>
            ))}
          </CarouselTrack>

          {accounts.length > 1 && (
            <CarouselChevron
              direction="right"
              disabled={index >= accounts.length - 1}
              onClick={() => select(index + 1)}
              label="Next account"
            />
          )}
        </div>

        <CarouselPosition index={index} count={accounts.length} label={active?.name} />

        <ActivitySection
          account={active}
          rows={rows}
          loading={loadingActivity}
          hidden={hidden}
        />
      </div>

      {/* -------------------------------------------------- desktop: master/detail */}
      <div className="hidden gap-6 lg:grid lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <nav aria-label="Your accounts" className="space-y-2">
          {accounts.map((account, i) => (
            <button
              key={account.id}
              onClick={() => select(i)}
              aria-current={i === index}
              className={`pressable pressable-surface w-full rounded-card border px-4 py-3 text-left ${
                i === index
                  ? "border-accent/40 bg-accent-muted"
                  : "border-white/5 bg-surface-primary hover:bg-surface-elevated"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 truncate text-sm font-medium text-content-primary">
                    {account.is_favorite && (
                      <Icon name="star" size={13} filled className="shrink-0 text-accent" />
                    )}
                    {account.name}
                  </p>
                  <p className="mt-0.5 text-xs text-content-secondary">
                    {account.account_type.replace(/_/g, " ")}
                  </p>
                </div>
                <MoneyValue
                  amount={account.balance}
                  currency={account.currency}
                  tone={account.account_nature === "LIABILITY" ? "expense" : "neutral"}
                  hidden={hidden}
                />
              </div>
            </button>
          ))}
        </nav>

        <div>
          {active && (
            <AccountPanel
              account={active}
              hidden={hidden}
              onFavoriteChanged={loadAccounts}
            />
          )}
          <ActivitySection
            account={active}
            rows={rows}
            loading={loadingActivity}
            hidden={hidden}
          />
        </div>
      </div>
    </AppShell>
  );
}

function ActivitySection({
  account,
  rows,
  loading,
  hidden,
}: {
  account: Account | undefined;
  rows: Transaction[] | undefined;
  loading: boolean;
  hidden: boolean;
}) {
  if (!account) return null;

  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-section">Recent activity</h2>
        <Link href={`/transactions?account=${account.id}`} className="text-xs text-accent">
          View all
        </Link>
      </div>

      {rows === undefined && loading ? (
        <Skeleton className="h-40 w-full" />
      ) : !rows || rows.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          message={`No transactions recorded on ${account.name}.`}
          action={
            <Link href={`/add?account=${account.id}`}>
              <Button>Add transaction</Button>
            </Link>
          }
        />
      ) : (
        <Card>
          {rows.map((t) => (
            <TransactionRow key={t.id} transaction={t} hidden={hidden} showAccount={false} />
          ))}
        </Card>
      )}
    </section>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Accounts />
      </RequireSession>
    </Providers>
  );
}
