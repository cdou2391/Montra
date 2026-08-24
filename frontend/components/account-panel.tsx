"use client";

/**
 * The large single-account panel shared by the mobile carousel and the desktop
 * master/detail layout (UI/UX sections 31, 33).
 *
 * The whole panel is deliberately not a link: on mobile it lives inside a
 * swipeable track, where a tap target that large fights the gesture.
 */

import Link from "next/link";
import { useState } from "react";

import { Account, montra } from "@/lib/api";
import { MoneyValue } from "@/components/financial";
import { Icon } from "@/components/icons";
import { Card, StatusChip } from "@/components/ui";

/** Star toggle. Optimistic, because a star that lags a tap feels broken. */
function FavoriteToggle({
  account,
  onChanged,
}: {
  account: Account;
  onChanged?: () => void;
}) {
  const [favorite, setFavorite] = useState(account.is_favorite);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    const next = !favorite;
    setFavorite(next);
    setBusy(true);
    try {
      if (next) await montra.setFavoriteAccount(account.id);
      else await montra.clearFavoriteAccount(account.id);
      onChanged?.();
    } catch {
      setFavorite(!next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={busy}
      aria-pressed={favorite}
      aria-label={favorite ? `Unstar ${account.name}` : `Make ${account.name} my favourite`}
      className={`pressable pressable-tint flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
        favorite ? "text-accent" : "text-content-muted"
      }`}
    >
      <Icon name="star" size={20} filled={favorite} />
    </button>
  );
}

export function AccountPanel({
  account,
  hidden,
  onFavoriteChanged,
}: {
  account: Account;
  hidden?: boolean;
  onFavoriteChanged?: () => void;
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
        <div className="flex shrink-0 items-center gap-2">
          {isLiability && <StatusChip tone="expense">Credit</StatusChip>}
          <FavoriteToggle account={account} onChanged={onFavoriteChanged} />
        </div>
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
          className="pressable min-h-[40px] rounded-control bg-accent px-4 text-sm font-semibold leading-10 text-background-primary"
        >
          Add
        </Link>
        <Link
          href={`/transfer?from=${account.id}`}
          className="pressable pressable-tint min-h-[40px] rounded-control border border-white/15 px-4 text-sm font-medium leading-10 text-content-primary"
        >
          Transfer
        </Link>
        <Link
          href={`/accounts/${account.id}`}
          className="pressable min-h-[40px] px-2 text-sm font-medium leading-10 text-accent"
        >
          Details
        </Link>
      </div>
    </Card>
  );
}
