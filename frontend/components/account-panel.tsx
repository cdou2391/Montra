"use client";

/**
 * The large single-account panel shared by the mobile carousel and the desktop
 * master/detail layout (UI/UX sections 31, 33).
 *
 * The whole panel is the link to the account. Inside a swipeable track that is
 * safe: a drag scrolls and suppresses the click, a tap navigates.
 */

import Link from "next/link";
import { useState } from "react";

import { Account, montra } from "@/lib/api";
import { MoneyValue } from "@/components/financial";
import { Icon, accountTypeIcon } from "@/components/icons";
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

  async function toggle(event: React.MouseEvent) {
    // The star sits inside the link to the account; starring is not navigating.
    event.preventDefault();
    event.stopPropagation();

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
    <Link
      href={`/accounts/${account.id}`}
      aria-label={`${account.name} details`}
      className="pressable pressable-surface block"
    >
      <Card className="flex min-h-[150px] flex-col justify-between transition-colors hover:bg-surface-elevated">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            {/* Restrained: the accent stays reserved for meaning, not decoration
                (UI/UX section 9). */}
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/5 text-content-secondary">
              <Icon name={accountTypeIcon(account.account_type)} size={20} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-section text-content-primary">{account.name}</p>
              {/* One line: with the icon taking width, this wrapped at 320px
                  and made the card taller than the balance it exists to show. */}
              <p className="mt-1 truncate text-xs text-content-secondary">
                {account.account_type.replace(/_/g, " ")}
                {account.masked_identifier ? ` · ${account.masked_identifier}` : ""}
              </p>
            </div>
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
      </Card>
    </Link>
  );
}
