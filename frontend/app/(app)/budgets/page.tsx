"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { BudgetRow, BudgetStatus, Category, MontraApiError, montra } from "@/lib/api";
import { ContextSwitch, useFinancialContext } from "@/components/context";
import { PageHeader } from "@/components/shell";
import { useSession } from "@/components/session";
import {
  AmountInput,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Field,
  Select,
  Skeleton,
} from "@/components/ui";
import { formatMoney } from "@/lib/format";

/**
 * Budgets.
 *
 * Everything shown is derived server-side from the ledger, so nothing here
 * does financial arithmetic of its own beyond laying the numbers out.
 */

const TONE: Record<BudgetRow["state"], { bar: string; text: string }> = {
  UNDER: { bar: "bg-accent", text: "text-content-secondary" },
  NEAR: { bar: "bg-semantic-warning", text: "text-semantic-warning" },
  OVER: { bar: "bg-semantic-expense", text: "text-semantic-expense" },
};

function BudgetCard({ row, onChanged }: { row: BudgetRow; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const tone = TONE[row.state];
  const used = Number(row.used_percent);
  const over = row.state === "OVER";
  const remaining = Number(row.remaining);

  // The bar stops at the limit; the number beside it is what says by how much
  // the limit was passed.
  const width = Math.max(0, Math.min(100, used));

  async function archive() {
    setBusy(true);
    try {
      await montra.archiveBudget(row.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="truncate text-sm font-medium text-content-primary">{row.category.name}</p>
        <p className={`tabular shrink-0 text-sm font-semibold ${tone.text}`}>
          {formatMoney(row.spent, row.currency)}
          <span className="font-normal text-content-muted">
            {" "}
            / {formatMoney(row.amount, row.currency)}
          </span>
        </p>
      </div>

      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-line/10">
        <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${width}%` }} />
      </div>

      <p className="mt-2 text-xs text-content-secondary">
        {over
          ? `${formatMoney(String(Math.abs(remaining)), row.currency)} over`
          : `${formatMoney(row.remaining, row.currency)} left`}
        {" · "}
        {row.used_percent}% used
      </p>

      {/* Only worth saying while there is still a month left to act on it. */}
      {row.state !== "OVER" && Number(row.projected) > Number(row.amount) && (
        <p className="mt-1 text-xs text-semantic-warning">
          At this pace you will reach {formatMoney(row.projected, row.currency)} by month end.
        </p>
      )}

      <div className="mt-3">
        <button
          type="button"
          onClick={archive}
          disabled={busy}
          className="pressable pressable-tint min-h-[36px] rounded-full border border-line/10 px-3 text-xs text-content-secondary disabled:opacity-40"
        >
          Remove
        </button>
      </div>
    </Card>
  );
}

export default function Budgets() {
  const { user } = useSession();
  const { context, family } = useFinancialContext();
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [adding, setAdding] = useState(false);
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [visibility, setVisibility] = useState("PRIVATE");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    montra
      .budgets(context)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [context]);

  useEffect(load, [load]);
  useEffect(() => {
    montra
      .categories("EXPENSE")
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  const currency = status?.currency ?? user?.base_currency ?? "RWF";
  // A category that already has one cannot have a second, so it is not offered.
  const spoken = new Set((status?.budgets ?? []).map((b) => b.category.id));
  const available = categories.filter((c) => !spoken.has(c.id));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await montra.createBudget({ category_id: categoryId, amount, visibility });
      setAdding(false);
      setCategoryId("");
      setAmount("");
      load();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not add that budget.");
    } finally {
      setSaving(false);
    }
  }

  if (status === null) {
    return (
      <>
        <PageHeader title="Budgets" icon="scale" />
        <Skeleton className="h-48 w-full" />
      </>
    );
  }

  return (
    <>
      {family && <ContextSwitch className="mb-5" />}

      <PageHeader
        title="Budgets"
        icon="scale"
        action={
          available.length > 0 && (
            <Button onClick={() => setAdding((v) => !v)}>{adding ? "Cancel" : "Add"}</Button>
          )
        }
      />

      {adding && (
        <Card className="mb-4">
          <form onSubmit={submit} className="space-y-4">
            {error && <ErrorNotice message={error} />}
            <Field label="Category">
              <Select
                required
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
              >
                <option value="">Choose a category</option>
                {available.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Monthly limit" hint={`In ${currency}. Resets on the 1st.`}>
              <AmountInput
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>

            {/* Only where there is a household to share with: the API refuses
                otherwise, and an option that always errors is worse than no
                option. Same words the Household page uses. */}
            {family && (
              <Field
                label="Who can see it"
                hint="Shared means the household can add to it too."
              >
                <Select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                >
                  <option value="PRIVATE">Only me</option>
                  <option value="FAMILY_VISIBLE">Household can see</option>
                  <option value="SHARED">Shared</option>
                </Select>
              </Field>
            )}
            <Button type="submit" disabled={saving || !categoryId || !amount}>
              {saving ? "Adding…" : "Add budget"}
            </Button>
          </form>
        </Card>
      )}

      {status.budgets.length === 0 ? (
        <EmptyState
          title="No budgets yet"
          message="Set a monthly limit on a category and this page will track what you have spent against it."
          action={
            !adding && (
              <Button onClick={() => setAdding(true)}>Add a budget</Button>
            )
          }
        />
      ) : (
        <>
          {status.totals && (
            <Card className="mb-4">
              <p className="text-sm text-content-secondary">
                Spent this month, across {status.budgets.length} budget
                {status.budgets.length === 1 ? "" : "s"}
              </p>
              <p className="mt-2">
                <span className="tabular text-value sm:text-value-lg">
                  {formatMoney(status.totals.spent, currency)}
                </span>
                <span className="text-sm text-content-muted">
                  {" "}
                  of {formatMoney(status.totals.amount, currency)}
                </span>
              </p>
              {status.unconverted_currencies.length > 0 && (
                <p className="mt-2 text-xs text-semantic-warning">
                  Not counting spending in{" "}
                  {status.unconverted_currencies.join(" and ")} —{" "}
                  <Link href="/settings" className="pressable underline">
                    set an exchange rate
                  </Link>
                  .
                </p>
              )}
            </Card>
          )}

          {/* Over first, then near: the ones that need a decision. */}
          {status.budgets.map((row) => (
            <BudgetCard key={row.id} row={row} onChanged={load} />
          ))}
        </>
      )}
    </>
  );
}
