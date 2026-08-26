"use client";

/**
 * Transactions as a table, for screens with room to scan columns.
 *
 * The phone list stacks each transaction into a block; here the same fields
 * become columns so a run of them can be compared down the page. Amounts are
 * right-aligned and tabular so the digits line up.
 */

import Link from "next/link";

import { Transaction } from "@/lib/api";
import { Card } from "@/components/ui";
import { formatDate, formatMoney, formatTime } from "@/lib/format";

const TONES: Record<string, string> = {
  INCOME: "text-semantic-income",
  EXPENSE: "text-semantic-expense",
  TRANSFER: "text-semantic-transfer",
  ADJUSTMENT: "text-content-secondary",
};

export function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full min-w-[44rem] text-sm">
        <caption className="sr-only">Transactions matching the current filters</caption>
        <thead>
          <tr className="border-b border-line/5 text-left text-xs uppercase tracking-wide text-content-muted">
            <th scope="col" className="px-4 py-3 font-normal">
              When
            </th>
            <th scope="col" className="px-4 py-3 font-normal">
              Description
            </th>
            <th scope="col" className="px-4 py-3 font-normal">
              Account
            </th>
            <th scope="col" className="px-4 py-3 font-normal">
              Category
            </th>
            <th scope="col" className="px-4 py-3 text-right font-normal">
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.id} className="border-b border-line/5 last:border-0 hover:bg-surface-elevated">
              <td className="whitespace-nowrap px-4 py-3 text-content-secondary">
                <span className="block">{formatDate(t.occurred_at)}</span>
                <span className="block text-xs text-content-muted">
                  {formatTime(t.occurred_at)}
                </span>
              </td>
              <td className="px-4 py-3">
                <Link
                  href={`/transactions/${t.id}`}
                  className="pressable font-medium text-content-primary hover:text-accent"
                >
                  {t.description || t.merchant || "Untitled"}
                </Link>
              </td>
              <td className="px-4 py-3 text-content-secondary">{t.account?.name ?? "—"}</td>
              <td className="px-4 py-3 text-content-secondary">{t.category?.name ?? "—"}</td>
              <td
                className={`tabular whitespace-nowrap px-4 py-3 text-right font-semibold ${
                  TONES[t.transaction_type] ?? "text-content-primary"
                }`}
              >
                {/* Colour says what kind of movement it was; the sign says
                    which way the account's own balance went. */}
                {t.direction === "DECREASE" ? "−" : "+"}
                {formatMoney(t.amount, t.currency).replace("-", "")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
