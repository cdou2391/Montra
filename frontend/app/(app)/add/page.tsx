"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { Account, Category, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";
import { toLocalInputValue } from "@/lib/format";

/**
 * Add income or expense.
 *
 * The form never decides a ledger direction; it sends a transaction type and
 * the backend's posting engine resolves the effect from the account's nature.
 */
function AddTransactionForm() {
  const router = useRouter();
  const params = useSearchParams();

  const [type, setType] = useState<"EXPENSE" | "INCOME">("EXPENSE");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [form, setForm] = useState({
    account_id: params.get("account") ?? "",
    amount: "",
    occurred_at: toLocalInputValue(),
    category_id: "",
    description: "",
    merchant: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.accounts().then((list) => {
      setAccounts(list);
      setForm((f) => ({ ...f, account_id: f.account_id || list[0]?.id || "" }));
    });
  }, []);

  useEffect(() => {
    montra.categories(type).then(setCategories);
    setForm((f) => ({ ...f, category_id: "" }));
  }, [type]);

  const selected = accounts.find((a) => a.id === form.account_id);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.createTransaction({
        transaction_type: type,
        account_id: form.account_id,
        amount: form.amount,
        occurred_at: form.occurred_at,
        category_id: form.category_id || null,
        description: form.description || null,
        merchant: form.merchant || null,
      });
      router.push("/transactions");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof MontraApiError ? err.message : "Could not save the transaction.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Add transaction"
        icon="plus" />

      <div className="mb-5 grid grid-cols-2 gap-2 rounded-control bg-background-secondary p-1">
        {(["EXPENSE", "INCOME"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={`min-h-[44px] rounded-[10px] text-sm font-semibold transition ${
              type === t
                ? t === "EXPENSE"
                  ? "bg-semantic-expense/15 text-semantic-expense"
                  : "bg-semantic-income/15 text-semantic-income"
                : "text-content-secondary"
            }`}
          >
            {t === "EXPENSE" ? "Expense" : "Income"}
          </button>
        ))}
      </div>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="Amount">
            <AmountInput
              required
              placeholder="0"
              value={form.amount}
              onChange={(e) => update("amount", e.target.value)}
            />
          </Field>
          <Field
            label="Account"
            hint={
              selected?.account_nature === "LIABILITY" && type === "EXPENSE"
                ? "This card purchase will increase the amount you owe."
                : undefined
            }
          >
            <Select
              required
              value={form.account_id}
              onChange={(e) => update("account_id", e.target.value)}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Category">
            <Select
              value={form.category_id}
              onChange={(e) => update("category_id", e.target.value)}
            >
              <option value="">Uncategorised</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="When" hint="Defaults to now. Change it for something you are recording after the fact.">
            <Input
              type="datetime-local"
              required
              value={form.occurred_at}
              onChange={(e) => update("occurred_at", e.target.value)}
            />
          </Field>
          <Field label="Description">
            <Input
              value={form.description}
              placeholder="Simba Supermarket"
              onChange={(e) => update("description", e.target.value)}
            />
          </Field>
          <div className="flex gap-3">
            <Button type="submit" disabled={busy || !form.account_id} className="flex-1">
              {busy ? "Saving…" : `Add ${type === "EXPENSE" ? "expense" : "income"}`}
            </Button>
            <Button variant="secondary" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AddTransactionForm />
    </Suspense>
  );
}
