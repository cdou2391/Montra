"use client";

/**
 * The large single-account panel shared by the mobile carousel and the desktop
 * master/detail layout (UI/UX sections 31, 33).
 *
 * The whole panel is deliberately not a link: on mobile it lives inside a
 * swipeable track, where a tap target that large fights the gesture.
 */

import Link from "next/link";

import { Account } from "@/lib/api";
import { MoneyValue } from "@/components/financial";
import { Card, StatusChip } from "@/components/ui";

export function AccountPanel({
  account,
  hidden,
}: {
  account: Account;
  hidden?: boolean;
}) {
  const isLiability = account.account_nature === "LIABILITY";

  return (
    <Card className="flex min-h-[188px] flex-col justify-between">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-section text-content-primary">{account.name}</p>
          <p className="mt-1 text-xs text-content-secondary">
            {account.account_type.replace(/_/g, " ")}
            {account.masked_identifier ? ` · ${account.masked_identifier}` : ""}
          </p>
        </div>
        {isLiability && <StatusChip tone="expense">Credit</StatusChip>}
      </div>

      <div className="mt-5">
        {/* A liability balance is debt owed, never money available. */}
        <p className="text-xs uppercase tracking-wide text-content-muted">
          {isLiability ? "Balance owed" : "Available"}
        </p>
        <p className="mt-1">
          <MoneyValue
            amount={account.balance}
            currency={account.currency}
            size="value"
            hidden={hidden}
          />
        </p>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <Link
          href={`/add?account=${account.id}`}
          className="min-h-[40px] rounded-control bg-accent px-4 text-sm font-semibold leading-10 text-background-primary"
        >
          Add
        </Link>
        <Link
          href={`/transfer?from=${account.id}`}
          className="min-h-[40px] rounded-control border border-white/15 px-4 text-sm font-medium leading-10 text-content-primary"
        >
          Transfer
        </Link>
        <Link
          href={`/accounts/${account.id}`}
          className="min-h-[40px] px-2 text-sm font-medium leading-10 text-accent"
        >
          Details
        </Link>
      </div>
    </Card>
  );
}
