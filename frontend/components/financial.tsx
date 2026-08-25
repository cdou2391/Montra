"use client";

/**
 * Financial display components (Implementation Plan Phase 1).
 *
 * Colour rule, UI/UX section 9: most monetary values stay off-white. Colour is
 * reserved for movement direction and status, not for every number on screen.
 */

import Link from "next/link";

import { Account, Transaction } from "@/lib/api";
import { formatDateTime, formatMoney } from "@/lib/format";
import { Icon, accountTypeIcon } from "@/components/icons";
import { Card, StatusChip } from "@/components/ui";

export function MoneyValue({
  amount,
  currency,
  tone = "neutral",
  size = "body",
  hidden = false,
}: {
  amount: string;
  currency: string;
  tone?: "neutral" | "income" | "expense" | "transfer";
  size?: "body" | "value" | "value-lg";
  hidden?: boolean;
}) {
  const tones = {
    neutral: "text-content-primary",
    income: "text-semantic-income",
    expense: "text-semantic-expense",
    transfer: "text-semantic-transfer",
  }[tone];
  const sizes = {
    body: "text-base font-medium",
    value: "text-[1.55rem] font-bold leading-tight sm:text-value",
    "value-lg": "text-value sm:text-value-lg",
  }[size];

  return (
    <span className={`tabular ${sizes} ${tones}`}>
      {hidden ? "••••••" : formatMoney(amount, currency)}
    </span>
  );
}

export function MetricCard({
  label,
  amount,
  currency,
  tone = "neutral",
  hidden,
}: {
  label: string;
  amount: string;
  currency: string;
  tone?: "neutral" | "income" | "expense";
  hidden?: boolean;
}) {
  return (
    <Card>
      <p className="text-sm text-content-secondary">{label}</p>
      <p className="mt-2">
        <MoneyValue amount={amount} currency={currency} tone={tone} hidden={hidden} />
      </p>
    </Card>
  );
}

/**
 * What is left to spend on a card.
 *
 * The balance beside it answers "how much do I owe"; this answers "how much
 * can I still put on it", which is the question people act on. Comes from the
 * API rather than being subtracted here, so one place decides it.
 */
function CardHeadroom({ account, hidden }: { account: Account; hidden?: boolean }) {
  const card = account.credit_card;
  if (!card || card.available_credit === null) return null;

  const left = Number(card.available_credit);
  const over = left < 0;
  return (
    <p className={`mt-1 text-xs ${over ? "text-semantic-expense" : "text-content-secondary"}`}>
      {hidden
        ? "••••"
        : `${formatMoney(String(Math.abs(left)), account.currency)} ${over ? "over limit" : "left"}`}
    </p>
  );
}

export function AccountCard({ account, hidden }: { account: Account; hidden?: boolean }) {
  const isLiability = account.account_nature === "LIABILITY";
  return (
    <Link href={`/accounts/${account.id}`} className="pressable pressable-surface block">
      <Card className="transition-colors hover:bg-surface-elevated">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 text-content-secondary">
              <Icon name={accountTypeIcon(account.account_type)} size={18} />
            </span>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 truncate font-medium text-content-primary">
                {account.is_favorite && (
                  <Icon name="star" size={14} filled className="shrink-0 text-accent" />
                )}
                {account.name}
              </p>
              <p className="mt-1 truncate text-xs text-content-secondary">
                {account.account_type.replace(/_/g, " ")}
                {account.masked_identifier ? ` · ${account.masked_identifier}` : ""}
              </p>
            </div>
          </div>
          <div className="text-right">
            <MoneyValue
              amount={account.balance}
              currency={account.currency}
              hidden={hidden}
            />
            {/* A liability balance is debt owed, not money held. Labelling it
                avoids reading a card balance as available funds. */}
            <p className="mt-1 text-xs text-content-muted">
              {isLiability ? "Owed" : "Available"}
            </p>
            <CardHeadroom account={account} hidden={hidden} />
          </div>
        </div>
      </Card>
    </Link>
  );
}

/**
 * Compact account tile for a scrolling row.
 *
 * Narrower than the full-width card so several are visible at once, which is
 * the point: the row is for comparing accounts at a glance, not for reading
 * one in detail. Type, masked number, the owed/available label and a card's
 * remaining credit are all dropped — the icon carries the type, and the
 * account's own screen carries the rest.
 */
export function AccountTile({ account, hidden }: { account: Account; hidden?: boolean }) {
  return (
    <Link
      href={`/accounts/${account.id}`}
      className="pressable pressable-surface w-[13.5rem] shrink-0 snap-start"
    >
      <Card className="flex h-full items-start gap-3 transition-colors hover:bg-surface-elevated">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 text-content-secondary">
          <Icon name={accountTypeIcon(account.account_type)} size={18} />
        </span>
        {/* min-w-0 so a long account name truncates instead of pushing the
            amount out of the tile. */}
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-sm font-medium text-content-primary">
            {account.is_favorite && (
              <Icon name="star" size={13} filled className="shrink-0 text-accent" />
            )}
            <span className="truncate">{account.name}</span>
          </p>
          <p className="mt-1.5">
            <MoneyValue amount={account.balance} currency={account.currency} hidden={hidden} />
          </p>
        </div>
      </Card>
    </Link>
  );
}

export function TransactionRow({
  transaction,
  hidden,
  showAccount = true,
}: {
  transaction: Transaction;
  hidden?: boolean;
  /** Off when the surrounding view already names the account. */
  showAccount?: boolean;
}) {
  const { transaction_type: type, direction } = transaction;

  // Colour states what kind of event this was; sign states which way it moved
  // THIS account's own balance. The two must be derived separately: on a credit
  // card a purchase raises the balance owed, so direction is INCREASE while the
  // event is still spending. Colouring by direction alone paints card purchases
  // green, as though buying groceries were income.
  const tone =
    type === "TRANSFER"
      ? "transfer"
      : type === "ADJUSTMENT"
        ? "neutral"
        : type === "INCOME"
          ? "income"
          : "expense";
  const sign = direction === "INCREASE" ? "+" : "−";

  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/5 py-3 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-content-primary">
          {transaction.description ?? transaction.merchant ?? type}
        </p>
        <p className="mt-0.5 truncate text-xs text-content-secondary">
          {formatDateTime(transaction.occurred_at)}
          {transaction.category ? ` · ${transaction.category.name}` : ""}
          {showAccount && transaction.account ? ` · ${transaction.account.name}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {transaction.status !== "COMPLETED" && (
          <StatusChip tone="warning">{transaction.status}</StatusChip>
        )}
        <span
          className={`tabular text-sm font-semibold ${
            {
              transfer: "text-semantic-transfer",
              income: "text-semantic-income",
              expense: "text-semantic-expense",
              neutral: "text-content-secondary",
            }[tone]
          }`}
        >
          {hidden ? "••••" : `${sign}${formatMoney(transaction.amount, transaction.currency)}`}
        </span>
      </div>
    </div>
  );
}
