"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Account, Transaction, montra } from "@/lib/api";
import { ContextSwitch, useFinancialContext } from "@/components/context";
import { AccountsSkeleton, SkeletonRows } from "@/components/skeletons";
import { PageHeader } from "@/components/shell";
import { BalancePrivacyToggle, useBalancePrivacy } from "@/components/balance-privacy";
import { MoneyValue, TransactionRow } from "@/components/financial";
import { AccountPanel } from "@/components/account-panel";
import { Icon, accountTypeIcon } from "@/components/icons";
import {
  CarouselChevron,
  CarouselPosition,
  CarouselSlide,
  CarouselTrack,
  useCarousel,
} from "@/components/carousel";
import { Button, Card, EmptyState } from "@/components/ui";

const RECENT_LIMIT = 6;

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const { hidden } = useBalancePrivacy();

  // Recent activity is cached per account so swiping back and forth does not
  // refetch what we already have.
  const [activity, setActivity] = useState<Record<string, Transaction[]>>({});
  const [loadingActivity, setLoadingActivity] = useState(false);
  const inFlight = useRef<Set<string>>(new Set());

  const { trackRef, index, onScroll, select } = useCarousel(accounts?.length ?? 0);
  const active = accounts?.[index];

  const { context, family } = useFinancialContext();

  const loadAccounts = useCallback(() => {
    montra.accounts(context).then(setAccounts).catch(() => setAccounts([]));
  }, [context]);

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

  // The same header in every state: its title and actions do not depend on
  // the data, so rendering a lesser one first only makes the bar rearrange.
  const header = (
    <PageHeader
      title="Accounts"
      icon="wallet"
      action={
        <>
          <Link href="/accounts/new">
            <Button>
              <span className="sm:hidden">Add</span>
              <span className="hidden sm:inline">New account</span>
            </Button>
          </Link>
          {/* Last in the action slot, so it sits immediately left of the bell
              — the same place Home puts it. */}
          <BalancePrivacyToggle />
        </>
      }
    />
  );

  if (accounts === null) {
    return (
      <>
        {header}
        <AccountsSkeleton />
      </>
    );
  }

  if (accounts.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          title="No accounts yet"
          message="Add a bank account, cash, mobile money or a card to get started."
          action={
            <Link href="/accounts/new">
              <Button>Add account</Button>
            </Link>
          }
        />
      </>
    );
  }

  const rows = active ? activity[active.id] : undefined;

  return (
    <>
      {family && <ContextSwitch className="mb-5" />}

      {header}

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
                  : "border-line/5 bg-surface-primary hover:bg-surface-elevated"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-line/5 text-content-secondary">
                    <Icon name={accountTypeIcon(account.account_type)} size={16} />
                  </span>
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
    </>
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
        <Link href={`/transactions?account=${account.id}`} className="pressable text-xs text-accent">
          View all
        </Link>
      </div>

      {/* Actions live with the activity they produce, rather than on the card,
          which is now the link to the account.

          Hidden entirely when the account is only visible to you: offering an
          action the server will refuse is worse than not offering it. A
          FAMILY_VISIBLE account belonging to someone else is readable, not
          writable. */}
      {account.can_transact ? (
        <div className="mb-3 flex gap-2">
          <Link
            href={`/add?account=${account.id}`}
            className="pressable inline-flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-control bg-accent px-4 text-sm font-semibold text-background-primary"
          >
            <Icon name="plus" size={18} strokeWidth={2.2} />
            Add
          </Link>
          <Link
            href={`/transfer?from=${account.id}`}
            className="pressable pressable-tint inline-flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-control border border-line/15 px-4 text-sm font-medium text-content-primary"
          >
            <Icon name="transfer" size={18} />
            Transfer
          </Link>
        </div>
      ) : (
        <p className="mb-3 rounded-control border border-line/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
          Shared with you to view. Only the owner can record transactions here.
        </p>
      )}

      {rows === undefined && loading ? (
        <SkeletonRows rows={4} />
      ) : !rows || rows.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          message={`No transactions recorded on ${account.name}.`}
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
