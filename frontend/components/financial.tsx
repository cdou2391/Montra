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
    value: "text-value",
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

export function AccountCard({ account, hidden }: { account: Account; hidden?: boolean }) {
  const isLiability = account.account_nature === "LIABILITY";
  return (
    <Link href={`/accounts/${account.id}`} className="block">
      <Card className="transition hover:bg-surface-elevated">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate font-medium text-content-primary">{account.name}</p>
            <p className="mt-1 text-xs text-content-secondary">
              {account.account_type.replace(/_/g, " ")}
              {account.masked_identifier ? ` · ${account.masked_identifier}` : ""}
            </p>
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
          </div>
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
  const tone =
    type === "TRANSFER"
      ? "transfer"
      : direction === "INCREASE"
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
            tone === "transfer"
              ? "text-semantic-transfer"
              : tone === "income"
                ? "text-semantic-income"
                : "text-semantic-expense"
          }`}
        >
          {hidden ? "••••" : `${sign}${formatMoney(transaction.amount, transaction.currency)}`}
        </span>
      </div>
    </div>
  );
}
